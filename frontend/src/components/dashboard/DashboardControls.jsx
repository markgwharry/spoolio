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
      <div className="dashboard-controls">
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', marginBottom: 8 }}>
          {user.is_admin && <button className="button" onClick={onOpenDataManager}>Data Manager</button>}
          <button className="button" onClick={onOpenReport}>Supplies Report</button>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, marginLeft: 12 }}>
            <input type="checkbox" checked={hideEmpty} onChange={(event) => onHideEmptyChange(event.target.checked)} />
            Hide Empty Spools
          </label>
          <span style={{ marginLeft: 12, color: '#666' }}>
            Empty spools available: <strong>{emptySpoolCount}</strong>
          </span>
        </div>
        <DashboardFilters
          materials={materials}
          colors={colors}
          manufacturers={manufacturers}
          filters={filters}
          onChange={onFilterChange}
        />
      </div>
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
