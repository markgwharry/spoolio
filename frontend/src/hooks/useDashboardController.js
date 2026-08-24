import { useMemo, useState } from 'react';

const slug = (value) => String(value || '').toLowerCase().replace(/[^a-z0-9]+/g, '-');

export default function useDashboardController({
  user,
  data,
  mutations,
  onMessage,
}) {
  const [expanded, setExpanded] = useState({});
  const [collapsed, setCollapsed] = useState({});
  const [highlightedSpoolId, setHighlightedSpoolId] = useState(null);
  const [selectedSpool, setSelectedSpool] = useState(null);
  const [spoolHistory, setSpoolHistory] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [showDataManager, setShowDataManager] = useState(false);
  const [adminMetadata, setAdminMetadata] = useState(null);
  const [showReport, setShowReport] = useState(false);
  const [showAddSpool, setShowAddSpool] = useState(false);
  const names = useMemo(() => ({
    material: Object.fromEntries(data.materials.map((item) => [item.id, item.name])),
    color: Object.fromEntries(data.colors.map((item) => [item.id, item.name])),
  }), [data.materials, data.colors]);

  const refreshAdminMetadata = async () => {
    try {
      setAdminMetadata(await mutations.loadAdminMetadata());
    } catch (error) {
      onMessage(error.message || 'Failed to load metadata.');
    }
  };

  const openDataManager = async () => {
    if (!user?.is_admin) return;
    setShowDataManager(true);
    await refreshAdminMetadata();
  };

  const runAdminMutation = async (action) => {
    try {
      await action();
      await refreshAdminMetadata();
    } catch (error) {
      onMessage(error.message || 'Failed to update metadata.');
    }
  };

  const openSpoolDetail = async (spool) => {
    setSelectedSpool(spool);
    setLoadingHistory(true);
    try {
      setSpoolHistory(await mutations.loadSpoolHistory());
    } catch (error) {
      onMessage(error.message || 'Failed to fetch spool history.');
    } finally {
      setLoadingHistory(false);
    }
  };

  const expandSpoolGroup = (spool) => {
    const material = spool.materialName || names.material[spool.material_id] || '';
    const color = spool.colorName || names.color[spool.color_id] || '';
    const groupKey = `${material}-${color}`;
    setCollapsed((current) => ({ ...current, [material]: false }));
    setExpanded((current) => ({ ...current, [groupKey]: true }));
    return groupKey;
  };

  const jumpToSpoolGroup = (spool) => {
    const groupKey = expandSpoolGroup(spool);
    requestAnimationFrame(() => {
      const element = document.getElementById(`group-${slug(groupKey)}`);
      element?.scrollIntoView?.({ behavior: 'smooth', block: 'center' });
      element?.classList.add('jump-highlight');
      setTimeout(() => element?.classList.remove('jump-highlight'), 1200);
    });
  };

  const selectRackSpool = (spool) => {
    expandSpoolGroup(spool);
    setHighlightedSpoolId(spool.id);
    setTimeout(() => {
      document.getElementById(`spool-item-${spool.id}`)
        ?.scrollIntoView?.({ behavior: 'smooth', block: 'center' });
    }, 100);
    setTimeout(() => setHighlightedSpoolId(null), 3000);
  };

  const recordUsage = () => {
    const spoolId = selectedSpool?.id;
    setSelectedSpool(null);
    if (!spoolId) return;
    setHighlightedSpoolId(spoolId);
    setTimeout(() => {
      const element = document.getElementById(`spool-item-${spoolId}`);
      element?.scrollIntoView?.({ behavior: 'smooth', block: 'center' });
      element?.querySelector('.btn-primary')?.click();
    }, 100);
  };

  const updateSpool = (updated) => {
    const before = data.spools.find((spool) => spool.id === updated.id);
    data.setSpools((current) => current.map(
      (spool) => (spool.id === updated.id ? updated : spool),
    ));
    if (before && !before.is_empty && updated.is_empty) data.reloadEmptySpools();
  };

  const assembleRefill = async (refillId, emptySpoolId, spoolTypeId) => {
    try {
      const spool = await mutations.assembleRefill({
        refill_id: refillId,
        empty_spool_id: emptySpoolId,
        spool_type_id: spoolTypeId,
      });
      data.setSpools((current) => [...current, spool]);
      data.setRefills((current) => current.filter((refill) => refill.id !== refillId));
      if (emptySpoolId) {
        data.setEmptySpools((current) => current.filter(
          (emptySpool) => emptySpool.id !== emptySpoolId,
        ));
      }
    } catch (error) {
      onMessage(error.message || 'Error assembling refill');
    }
  };

  const deleteRefill = async (refillId) => {
    try {
      await mutations.deleteRefill(refillId);
      data.setRefills((current) => current.filter((refill) => refill.id !== refillId));
    } catch (error) {
      onMessage(error.message || 'Error deleting refill');
    }
  };

  const updateHistory = (updated) => {
    const entries = Array.isArray(updated) ? updated : [updated];
    setSpoolHistory((current) => current.map(
      (historyItem) => entries.find((entry) => entry.id === historyItem.id) || historyItem,
    ));
  };

  return {
    expanded,
    collapsed,
    highlightedSpoolId,
    selectedSpool,
    spoolHistory,
    loadingHistory,
    showDataManager,
    adminMetadata,
    showReport,
    showAddSpool,
    setShowDataManager,
    setShowReport,
    setShowAddSpool,
    setSelectedSpool,
    openDataManager,
    refreshAdminMetadata,
    runAdminMutation,
    openSpoolDetail,
    jumpToSpoolGroup,
    selectRackSpool,
    recordUsage,
    updateSpool,
    assembleRefill,
    deleteRefill,
    updateHistory,
    toggleGroup: (groupKey) => setExpanded((current) => ({
      ...current,
      [groupKey]: !current[groupKey],
    })),
    toggleMaterial: (material) => setCollapsed((current) => ({
      ...current,
      [material]: !current[material],
    })),
  };
}
