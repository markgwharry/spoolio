import React from 'react';
import AdminDataManager from './AdminDataManager';
import DashboardFilters from './DashboardFilters';

export default function DashboardControls({
  user,
  emptySpoolCount,
  hideEmpty,
  filters,
  materials,
  colors,
  manufacturers,
  showDataManager,
  adminMetadata,
  onHideEmptyChange,
  onFilterChange,
  onResetFilters,
  onOpenDataManager,
  onOpenReport,
  onCloseDataManager,
  onRefreshAdminMetadata,
  onUpdateSpoolType,
  onDeleteSpoolType,
  onDeleteManufacturer,
  onClearSubtype,
}) {
  return (
    <>
      <section className="dashboard-controls" aria-label="Filament library controls">
        <div className="dashboard-controls-heading">
          <div>
            <p className="eyebrow">Find filament</p>
            <h2>Filter your library</h2>
          </div>
          <details className="inventory-tools-menu">
            <summary>Inventory tools</summary>
            <div className="inventory-tools-content">
              {user.is_admin && <button className="button ghost" onClick={onOpenDataManager}>Data Manager</button>}
              <button className="button ghost" onClick={onOpenReport}>Supplies Report</button>
              <label className="filter-check">
                <input type="checkbox" checked={hideEmpty} onChange={(event) => onHideEmptyChange(event.target.checked)} />
                Hide empty groups
              </label>
              <span className="empty-spool-count">
                Empty spools: <strong>{emptySpoolCount}</strong>
              </span>
            </div>
          </details>
        </div>
        <DashboardFilters
          materials={materials}
          colors={colors}
          manufacturers={manufacturers}
          filters={filters}
          onChange={onFilterChange}
          onReset={onResetFilters}
        />
      </section>
      {user.is_admin && showDataManager && (
        <AdminDataManager
          metadata={adminMetadata}
          onClose={onCloseDataManager}
          onRefresh={onRefreshAdminMetadata}
          onUpdateSpoolType={onUpdateSpoolType}
          onDeleteSpoolType={onDeleteSpoolType}
          onDeleteManufacturer={onDeleteManufacturer}
          onClearSubtype={onClearSubtype}
        />
      )}
    </>
  );
}
