import React from 'react';
import FirmwareReleaseAdmin from '../../FirmwareReleaseAdmin';

const panelStyle = {
  background: 'var(--popover)',
  border: '1px solid var(--border)',
  borderRadius: 12,
  padding: 12,
  color: 'var(--popover-foreground)',
};

const deleteButtonStyle = (disabled) => ({
  background: disabled ? 'var(--muted)' : 'var(--destructive)',
  color: disabled ? 'var(--muted-foreground)' : 'var(--destructive-foreground)',
  border: 'none',
  cursor: disabled ? 'not-allowed' : 'pointer',
  opacity: disabled ? 0.7 : 1,
});

export default function AdminDataManager({
  metadata,
  onClose,
  onRefresh,
  onUpdateSpoolType,
  onDeleteSpoolType,
  onDeleteManufacturer,
  onClearSubtype,
}) {
  return (
    <div style={{
      margin: '16px 0',
      padding: '12px',
      border: '1px solid var(--border)',
      borderRadius: 12,
      background: 'var(--card)',
      color: 'var(--card-foreground)',
      boxShadow: '0 12px 32px rgba(7, 16, 32, 0.18)',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3 style={{ margin: 0 }}>Data Manager</h3>
        <div>
          <button onClick={onRefresh} style={{ marginRight: 8 }}>Refresh</button>
          <button onClick={onClose}>Close</button>
        </div>
      </div>
      {!metadata ? (
        <div>Loading…</div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginTop: 12 }}>
          <div style={panelStyle}>
            <h4 style={{ marginTop: 0 }}>Spool Types</h4>
            <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
              {metadata.spool_types.map((spoolType) => {
                const inUse = spoolType.num_spools > 0;
                return (
                  <li key={spoolType.id} style={{ marginBottom: 8 }}>
                    <div>
                      <strong>{spoolType.name}</strong> — tare: {spoolType.tare_weight || 0} g — in use: {spoolType.num_spools}
                    </div>
                    <div style={{ marginTop: 6 }}>
                      <input
                        type="number"
                        min="0"
                        step="0.1"
                        placeholder="Update tare (g)"
                        onBlur={(event) => onUpdateSpoolType(spoolType.id, {
                          tare_weight: parseFloat(event.target.value || 0),
                        })}
                        style={{ width: 120, marginRight: 8 }}
                      />
                      <input
                        type="text"
                        placeholder="Rename"
                        onBlur={(event) => event.target.value && onUpdateSpoolType(
                          spoolType.id,
                          { name: event.target.value },
                        )}
                        style={{ width: 160, marginRight: 8 }}
                      />
                      <button
                        onClick={() => onDeleteSpoolType(spoolType.id)}
                        disabled={inUse}
                        style={deleteButtonStyle(inUse)}
                      >
                        Delete
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
          <div style={panelStyle}>
            <h4 style={{ marginTop: 0 }}>Manufacturers</h4>
            <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
              {metadata.manufacturers.map((manufacturer) => {
                const inUse = manufacturer.num_spools > 0;
                return (
                  <li key={manufacturer.id} style={{ marginBottom: 8 }}>
                    <div><strong>{manufacturer.name}</strong> — in use: {manufacturer.num_spools}</div>
                    <div style={{ marginTop: 6 }}>
                      <button
                        onClick={() => onDeleteManufacturer(manufacturer.id)}
                        disabled={inUse}
                        style={deleteButtonStyle(inUse)}
                      >
                        Delete
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
          <div style={panelStyle}>
            <h4 style={{ marginTop: 0 }}>Subtypes</h4>
            <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
              {metadata.subtypes.map((subtype) => (
                <li key={subtype.name} style={{ marginBottom: 8 }}>
                  <div><strong>{subtype.name}</strong> — used by: {subtype.num_spools} spool(s)</div>
                  <div style={{ marginTop: 6 }}>
                    <button
                      onClick={() => onClearSubtype(subtype.name)}
                      style={{
                        background: 'var(--destructive)',
                        color: 'var(--destructive-foreground)',
                        border: 'none',
                      }}
                    >
                      Clear from my spools
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </div>
          {metadata.features?.firmware_ota && <FirmwareReleaseAdmin />}
        </div>
      )}
    </div>
  );
}
