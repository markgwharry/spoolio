import { useCallback, useMemo, useState } from 'react';
import { groupSpoolsByMaterialColor } from '../utils/colorUtils';

const initialFilters = {
  materialId: '',
  colorId: '',
  manufacturerId: '',
  subtypeMode: 'all',
  lowStockOnly: false,
  includeRefills: true,
  sortMode: 'rainbow',
};

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
  const [filters, setFilters] = useState(initialFilters);
  const [hideEmpty, setHideEmpty] = useState(false);
  const updateFilter = useCallback((name, value) => {
    setFilters((current) => ({ ...current, [name]: value }));
  }, []);

  const groupedSpools = useMemo(() => {
    const grouped = groupSpoolsByMaterialColor(
      spools,
      materials,
      colors,
      manufacturers,
      spoolTypes,
      hideEmpty,
      refills,
    );
    return sortGroupedSpools(grouped, filters.sortMode);
  }, [
    spools,
    materials,
    colors,
    manufacturers,
    spoolTypes,
    hideEmpty,
    refills,
    filters.sortMode,
  ]);

  return {
    filters,
    updateFilter,
    hideEmpty,
    setHideEmpty,
    groupedSpools,
  };
}
