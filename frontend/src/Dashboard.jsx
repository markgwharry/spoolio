import React, { useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { AuthContext } from './AuthContext';
import SpoolSpinner from './components/SpoolSpinner';
import AddSpoolModal from './components/dashboard/AddSpoolModal';
import DashboardControls from './components/dashboard/DashboardControls';
import DataEntryForms from './components/dashboard/DataEntryForms';
import InventoryOverview from './components/dashboard/InventoryOverview';
import MaterialSections from './components/dashboard/MaterialSections';
import SpoolDetailModal from './components/dashboard/SpoolDetailModal';
import StatsGrid from './components/dashboard/StatsGrid';
import SuppliesReport from './components/dashboard/SuppliesReport';
import useDashboardController from './hooks/useDashboardController';
import useDashboardData from './hooks/useDashboardData';
import useDashboardView from './hooks/useDashboardView';
import useSpoolMutations from './hooks/useSpoolMutations';

export default function Dashboard() {
  const { user, authFetch } = useContext(AuthContext);
  const data = useDashboardData(authFetch);
  const mutations = useSpoolMutations(authFetch);
  const [message, setMessage] = useState('');
  const safeSpools = useMemo(() => (Array.isArray(data.spools) ? data.spools : []), [data.spools]);
  const safeRefills = useMemo(() => (Array.isArray(data.refills) ? data.refills : []), [data.refills]);
  const safeEmptySpools = useMemo(
    () => (Array.isArray(data.emptySpools) ? data.emptySpools : []),
    [data.emptySpools],
  );
  const view = useDashboardView({
    spools: safeSpools,
    materials: data.materials,
    colors: data.colors,
    manufacturers: data.manufacturers,
    spoolTypes: data.spoolTypes,
    refills: safeRefills,
  });
  const controller = useDashboardController({ user, data, mutations, onMessage: setMessage });
  const setShowAddSpool = controller.setShowAddSpool;
  const location = useLocation();
  const navigate = useNavigate();
  const hasInventory = safeSpools.length > 0 || safeRefills.length > 0 || safeEmptySpools.length > 0;

  const handleJumpToSpool = useCallback((spool) => {
    view.resetFilters();
    window.requestAnimationFrame(() => controller.jumpToSpoolGroup(spool));
  }, [controller, view]);

  useEffect(() => {
    if (location.hash === '#add-spool') {
      setShowAddSpool(true);
      navigate(location.pathname + location.search, { replace: true });
    } else if (location.hash === '#find-spool') {
      if (data.loading || data.error || !hasInventory) return undefined;

      const frame = window.requestAnimationFrame(() => {
        const filter = document.getElementById('dashboard-filter-material');
        const controls = document.querySelector('.dashboard-controls');
        if (!filter || !controls) return;

        filter.focus();
        controls.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
        navigate(location.pathname + location.search, { replace: true });
      });
      return () => window.cancelAnimationFrame(frame);
    }
    return undefined;
  }, [data.error, data.loading, hasInventory, location, navigate, setShowAddSpool]);

  if (!user) return <div>Please log in.</div>;
  if (data.loading) return <SpoolSpinner label="Loading your inventory…" />;
  if (data.error) return <div>{data.error}</div>;

  return (
    <div className="dashboard-container">
      <InventoryOverview
        spools={safeSpools}
        refills={safeRefills}
        materials={data.materials}
        colors={data.colors}
        manufacturers={data.manufacturers}
        spoolTypes={data.spoolTypes}
        onAddSpool={() => setShowAddSpool(true)}
        onJumpToSpool={handleJumpToSpool}
      />
      <AddSpoolModal
        open={controller.showAddSpool}
        materials={data.materials}
        colors={data.colors}
        manufacturers={data.manufacturers}
        spoolTypes={data.spoolTypes}
        subtypes={data.subtypes}
        mutations={mutations}
        onMaterialAdded={(item) => data.setMaterials((current) => [...current, { id: item.id, name: item.name }])}
        onColorAdded={(item) => data.setColors((current) => [...current, { id: item.id, name: item.name }])}
        onManufacturerAdded={(item) => data.setManufacturers((current) => [...current, { id: item.id, name: item.name }])}
        onSpoolTypeAdded={(item) => data.setSpoolTypes((current) => [...current, {
          id: item.id,
          name: item.name,
          compatible_with_ams: item.compatible_with_ams,
          tare_weight: item.tare_weight,
        }])}
        onSpoolAdded={(spool) => data.setSpools((current) => [...current, spool])}
        onMessage={setMessage}
        onClose={() => setShowAddSpool(false)}
      />
      <SpoolDetailModal
        spool={controller.selectedSpool}
        history={controller.spoolHistory}
        loading={controller.loadingHistory}
        onClose={() => controller.setSelectedSpool(null)}
        onHistoryUpdate={controller.updateHistory}
        onRecordUsage={controller.recordUsage}
      />
      {message && <div className="toast" role="status">{message}</div>}
      <SuppliesReport
        open={controller.showReport}
        spools={safeSpools}
        refills={safeRefills}
        materials={data.materials}
        colors={data.colors}
        filters={view.filters}
        onClose={() => controller.setShowReport(false)}
      />
      {hasInventory && (
        <>
          <DashboardControls
            user={user}
            emptySpoolCount={safeEmptySpools.length}
            hideEmpty={view.hideEmpty}
            filters={view.filters}
            materials={data.materials}
            colors={data.colors}
            manufacturers={data.manufacturers}
            showDataManager={controller.showDataManager}
            adminMetadata={controller.adminMetadata}
            onHideEmptyChange={view.setHideEmpty}
            onFilterChange={view.updateFilter}
            onResetFilters={view.resetFilters}
            onOpenDataManager={controller.openDataManager}
            onOpenReport={() => controller.setShowReport(true)}
            onCloseDataManager={() => controller.setShowDataManager(false)}
            onRefreshAdminMetadata={controller.refreshAdminMetadata}
            onUpdateSpoolType={(id, fields) => controller.runAdminMutation(
              () => mutations.updateSpoolType(id, fields),
            )}
            onDeleteSpoolType={(id) => {
              if (window.confirm('Delete spool type? This is only allowed if unused.')) {
                controller.runAdminMutation(() => mutations.deleteSpoolType(id));
              }
            }}
            onDeleteManufacturer={(id) => {
              if (window.confirm('Delete manufacturer? This is only allowed if unused.')) {
                controller.runAdminMutation(() => mutations.deleteManufacturer(id));
              }
            }}
            onClearSubtype={(name) => {
              if (window.confirm(`Clear subtype "${name}" from all your spools?`)) {
                controller.runAdminMutation(async () => {
                  await mutations.clearSubtype(name);
                  await data.reloadSpools();
                });
              }
            }}
          />
          <MaterialSections
            groupedSpools={view.groupedSpools}
            spools={view.visibleSpools}
            refills={view.visibleRefills}
            emptySpools={safeEmptySpools}
            materials={data.materials}
            colors={data.colors}
            manufacturers={data.manufacturers}
            spoolTypes={data.spoolTypes}
            expanded={controller.expanded}
            collapsed={controller.collapsed}
            highlightedSpoolId={controller.highlightedSpoolId}
            onToggleGroup={controller.toggleGroup}
            onToggleMaterial={controller.toggleMaterial}
            onOpenSpoolDetail={controller.openSpoolDetail}
            onSpoolUpdated={controller.updateSpool}
            onSpoolDeleted={(id) => data.setSpools((current) => current.filter((spool) => spool.id !== id))}
            onAssembleRefill={controller.assembleRefill}
            onDeleteRefill={controller.deleteRefill}
          />
          <StatsGrid spools={safeSpools} emptySpools={safeEmptySpools} />
        </>
      )}
      <details className="inventory-entry-panel">
        <summary>Manage refills and empty spools</summary>
        <DataEntryForms
          materials={data.materials}
          colors={data.colors}
          manufacturers={data.manufacturers}
          spoolTypes={data.spoolTypes}
          addRefill={mutations.addRefill}
          addEmptySpool={mutations.addEmptySpool}
          onRefillAdded={(refill) => data.setRefills((current) => [...current, refill])}
          onEmptySpoolAdded={(emptySpool) => data.setEmptySpools((current) => [...current, emptySpool])}
          onError={setMessage}
        />
      </details>
    </div>
  );
}
