import React from 'react';

export default function DashboardFilters({
  materials,
  colors,
  manufacturers,
  filters,
  onChange,
}) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
      <select value={filters.materialId} onChange={(event) => onChange('materialId', event.target.value)}>
        <option value="">All materials</option>
        {materials.map((material) => (
          <option key={material.id} value={material.id}>{material.name}</option>
        ))}
      </select>
      <select value={filters.colorId} onChange={(event) => onChange('colorId', event.target.value)}>
        <option value="">All colors</option>
        {colors.map((color) => (
          <option key={color.id} value={color.id}>{color.name}</option>
        ))}
      </select>
      <select value={filters.manufacturerId} onChange={(event) => onChange('manufacturerId', event.target.value)}>
        <option value="">All manufacturers</option>
        {manufacturers.map((manufacturer) => (
          <option key={manufacturer.id} value={manufacturer.id}>{manufacturer.name}</option>
        ))}
      </select>
      <select value={filters.subtypeMode} onChange={(event) => onChange('subtypeMode', event.target.value)}>
        <option value="all">All subtypes</option>
        <option value="basic">Basic only</option>
        <option value="nonbasic">Non-basic only</option>
      </select>
      <select
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
      <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <input
          type="checkbox"
          checked={filters.lowStockOnly}
          onChange={(event) => onChange('lowStockOnly', event.target.checked)}
        />
        Low stock only
      </label>
      <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <input
          type="checkbox"
          checked={filters.includeRefills}
          onChange={(event) => onChange('includeRefills', event.target.checked)}
        />
        Include refills
      </label>
    </div>
  );
}
