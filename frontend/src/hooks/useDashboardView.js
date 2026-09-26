import { useCallback, useEffect, useMemo, useState } from 'react';
import { groupSpoolsByMaterialColor } from '../utils/colorUtils';

const VIEW_STORAGE_KEY = 'spoolio:dashboard-view';

const initialFilters = {
  materialId: '',
  colorId: '',
  manufacturerId: '',
  subtypeMode: 'all',
  lowStockOnly: false,
  includeRefills: true,
  sortMode: 'rainbow',
};

const readStoredView = () => {
  try {
    const stored = JSON.parse(localStorage.getItem(VIEW_STORAGE_KEY) || '{}');
    return {
      filters: { ...initialFilters, ...(stored.filters || {}) },
      hideEmpty: Boolean(stored.hideEmpty),
    };
  } catch {
    return { filters: initialFilters, hideEmpty: false };
  }
};

export function filterInventory(spools, refills, filters) {
  const subtypeMatches = (item) => {
    const hasSubtype = Boolean(String(item.subtype || '').trim());
    if (filters.subtypeMode === 'basic') return !hasSubtype;
    if (filters.subtypeMode === 'nonbasic') return hasSubtype;
    return true;
  };
  const sharedMatches = (item) => (
    (!filters.materialId || String(item.material_id) === String(filters.materialId))
    && (!filters.colorId || String(item.color_id) === String(filters.colorId))
    && (!filters.manufacturerId || String(item.manufacturer_id) === String(filters.manufacturerId))
    && subtypeMatches(item)
  );

  const visibleSpools = (Array.isArray(spools) ? spools : []).filter((spool) => (
    sharedMatches(spool)
    && (!filters.lowStockOnly || (
      !spool.is_empty
      && spool.weight_remaining <= (spool.low_stock_threshold ?? 100)
    ))
  ));
  const visibleRefills = filters.includeRefills
    ? (Array.isArray(refills) ? refills : []).filter((refill) => (
      sharedMatches(refill) && !filters.lowStockOnly
    ))
    : [];

  return { visibleSpools, visibleRefills };
}

export function sortGroupedSpools(grouped, sortMode) {
  const result = {};
  const materialWeight = (materialName) => Object.values(grouped[materialName] || {})
    .flat()
    .filter((spool) => !spool.is_empty)
    .reduce((sum, spool) => sum + (spool.weight_remaining || 0), 0);
  const colorWeight = (spools) => spools
    .filter((spool) => !spool.is_empty)
    .reduce((sum, spool) => sum + (spool.weight_remaining || 0), 0);
  const hasLowStock = (spools) => spools.some(
    (spool) => !spool.is_empty
      && spool.weight_remaining <= (spool.low_stock_threshold ?? 100),
  );

  const sortedMaterials = Object.keys(grouped);
  if (sortMode === 'alpha') {
    sortedMaterials.sort((a, b) => a.localeCompare(b));
  } else if (sortMode === 'weight-desc') {
    sortedMaterials.sort((a, b) => materialWeight(b) - materialWeight(a));
  } else if (sortMode === 'weight-asc') {
    sortedMaterials.sort((a, b) => materialWeight(a) - materialWeight(b));
  } else if (sortMode === 'low-stock') {
    sortedMaterials.sort((a, b) => {
      const aHasLow = Object.values(grouped[a] || {}).some(hasLowStock);
      const bHasLow = Object.values(grouped[b] || {}).some(hasLowStock);
      if (aHasLow !== bHasLow) return Number(bHasLow) - Number(aHasLow);
      return a.localeCompare(b);
    });
  }

  sortedMaterials.forEach((material) => {
    const colorGroups = grouped[material];
    const sortedColors = Object.keys(colorGroups);
    if (sortMode === 'alpha') {
      sortedColors.sort((a, b) => a.localeCompare(b));
    } else if (sortMode === 'weight-desc') {
      sortedColors.sort((a, b) => colorWeight(colorGroups[b]) - colorWeight(colorGroups[a]));
    } else if (sortMode === 'weight-asc') {
      sortedColors.sort((a, b) => colorWeight(colorGroups[a]) - colorWeight(colorGroups[b]));
    } else if (sortMode === 'low-stock') {
      sortedColors.sort((a, b) => {
        const aLow = hasLowStock(colorGroups[a]);
        const bLow = hasLowStock(colorGroups[b]);
        if (aLow !== bLow) return Number(bLow) - Number(aLow);
        return a.localeCompare(b);
      });
    }

    result[material] = Object.fromEntries(
      sortedColors.map((color) => [color, colorGroups[color]]),
    );
  });

  return result;
}

export default function useDashboardView({
  spools,
  materials,
  colors,
  manufacturers,
  spoolTypes,
  refills,
}) {
  const [storedView] = useState(readStoredView);
  const [filters, setFilters] = useState(storedView.filters);
  const [hideEmpty, setHideEmpty] = useState(storedView.hideEmpty);
  const updateFilter = useCallback((name, value) => {
    setFilters((current) => ({ ...current, [name]: value }));
  }, []);
  const resetFilters = useCallback(() => setFilters(initialFilters), []);

  useEffect(() => {
    try {
      localStorage.setItem(VIEW_STORAGE_KEY, JSON.stringify({ filters, hideEmpty }));
    } catch {}
  }, [filters, hideEmpty]);

  const { visibleSpools, visibleRefills } = useMemo(
    () => filterInventory(spools, refills, filters),
    [spools, refills, filters],
  );

  const groupedSpools = useMemo(() => {
    const grouped = groupSpoolsByMaterialColor(
      visibleSpools,
      materials,
      colors,
      manufacturers,
      spoolTypes,
      hideEmpty,
      visibleRefills,
    );
    return sortGroupedSpools(grouped, filters.sortMode);
  }, [
    visibleSpools,
    materials,
    colors,
    manufacturers,
    spoolTypes,
    hideEmpty,
    visibleRefills,
    filters.sortMode,
  ]);

  return {
    filters,
    updateFilter,
    resetFilters,
    hideEmpty,
    setHideEmpty,
    visibleSpools,
    visibleRefills,
    groupedSpools,
  };
}
