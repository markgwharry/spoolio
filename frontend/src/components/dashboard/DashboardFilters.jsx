import React from 'react';

export default function DashboardFilters({
  materials,
  colors,
  manufacturers,
  filters,
  onChange,
  onReset,
}) {
  const hasActiveFilters = Boolean(
    filters.materialId
    || filters.colorId
    || filters.manufacturerId
    || filters.subtypeMode !== 'all'
    || filters.lowStockOnly
    || !filters.includeRefills
    || filters.sortMode !== 'rainbow',
  );

  return (
    <div className="dashboard-filters" aria-label="Filter filament library">
      <select id="dashboard-filter-material" aria-label="Filter by material" value={filters.materialId} onChange={(event) => onChange('materialId', event.target.value)}>
        <option value="">All materials</option>
        {materials.map((material) => (
          <option key={material.id} value={material.id}>{material.name}</option>
        ))}
      </select>
      <select id="dashboard-filter-colour" aria-label="Filter by colour" value={filters.colorId} onChange={(event) => onChange('colorId', event.target.value)}>
        <option value="">All colours</option>
        {colors.map((color) => (
          <option key={color.id} value={color.id}>{color.name}</option>
        ))}
      </select>
      <select id="dashboard-filter-manufacturer" aria-label="Filter by manufacturer" value={filters.manufacturerId} onChange={(event) => onChange('manufacturerId', event.target.value)}>
        <option value="">All manufacturers</option>
        {manufacturers.map((manufacturer) => (
          <option key={manufacturer.id} value={manufacturer.id}>{manufacturer.name}</option>
        ))}
      </select>
      <select aria-label="Filter by subtype" value={filters.subtypeMode} onChange={(event) => onChange('subtypeMode', event.target.value)}>
        <option value="all">All subtypes</option>
        <option value="basic">Basic only</option>
        <option value="nonbasic">Non-basic only</option>
      </select>
      <select
        aria-label="Sort filament library"
        value={filters.sortMode}
        onChange={(event) => onChange('sortMode', event.target.value)}
        style={{ fontWeight: 500 }}
      >
        <option value="rainbow">Sort: Rainbow</option>
        <option value="alpha">Sort: A-Z</option>
        <option value="weight-desc">Sort: Weight ↓</option>
        <option value="weight-asc">Sort: Weight ↑</option>
        <option value="low-stock">Sort: Low Stock First</option>
      </select>
      <label className="filter-check">
        <input
          type="checkbox"
          checked={filters.lowStockOnly}
          onChange={(event) => onChange('lowStockOnly', event.target.checked)}
        />
        Low stock only
      </label>
      <label className="filter-check">
        <input
          type="checkbox"
          checked={filters.includeRefills}
          onChange={(event) => onChange('includeRefills', event.target.checked)}
        />
        Include refills
      </label>
      {hasActiveFilters && (
        <button type="button" className="button ghost filter-reset" onClick={onReset}>
          Clear filters
        </button>
      )}
    </div>
  );
}
