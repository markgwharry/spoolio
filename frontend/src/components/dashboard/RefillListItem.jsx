import React, { useState } from 'react';
import { formatGrams } from '../../utils/colorUtils';

export default function RefillListItem({ refill, manufacturers, onAssemble, onDelete, emptySpools, spoolTypes }) {
  const [assembling, setAssembling] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [selectedEmptyId, setSelectedEmptyId] = useState('');
  const [altSpoolTypeId, setAltSpoolTypeId] = useState('');
  const manufacturerMap = Object.fromEntries(manufacturers.map(m => [m.id, m.name]));
  const spoolTypeMap = Object.fromEntries(spoolTypes.map(s => [s.id, s.name]));

  const empties = emptySpools || [];
  const weight = formatGrams(refill.weight_remaining ?? refill.weight_total);
  const manufacturer = manufacturerMap[refill.manufacturer_id] || 'Unknown';
  const subtype = refill.subtype;

  if (!assembling) {
    return (
      <div className="refill-chip">
        <div className="refill-chip-info">
          <span className="refill-chip-weight">{weight}g</span>
          <span className="refill-chip-manufacturer">{manufacturer}</span>
          {subtype && <span className="refill-chip-subtype">{subtype}</span>}
        </div>
        <div className="refill-chip-actions">
          <button type="button" className="refill-chip-action" onClick={() => setAssembling(true)}>
            Bring into use
          </button>
          {confirmingDelete ? (
            <span className="refill-delete-confirm">
              <button type="button" className="refill-delete-yes" onClick={() => onDelete(refill.id)}>Delete</button>
              <button type="button" className="refill-delete-no" onClick={() => setConfirmingDelete(false)}>Cancel</button>
            </span>
          ) : (
            <button type="button" className="refill-chip-delete" onClick={() => setConfirmingDelete(true)} title="Delete refill">
              &times;
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="refill-chip assembling">
      <div className="refill-assemble-form">
        <span className="refill-chip-weight">{weight}g</span>
        <select value={selectedEmptyId} onChange={e => setSelectedEmptyId(e.target.value)}>
          <option value="">Empty spool...</option>
          {empties.map(e => (
            <option key={e.id} value={e.id}>
              {spoolTypeMap[e.spool_type_id] || 'Spool'} #{e.id}
            </option>
          ))}
        </select>
        <span className="refill-or">or</span>
        <select value={altSpoolTypeId} onChange={e => setAltSpoolTypeId(e.target.value)}>
          <option value="">New spool type...</option>
          {Object.entries(spoolTypeMap).map(([id, name]) => (
            <option key={id} value={id}>{name}</option>
          ))}
        </select>
        <button
          type="button"
          className="btn-assemble"
          disabled={!selectedEmptyId && !altSpoolTypeId}
          onClick={() => {
            if (selectedEmptyId) {
              onAssemble(refill.id, parseInt(selectedEmptyId, 10));
            } else if (altSpoolTypeId) {
              onAssemble(refill.id, undefined, parseInt(altSpoolTypeId, 10));
            }
          }}
        >
          Assemble
        </button>
        <button type="button" className="btn-cancel" onClick={() => setAssembling(false)}>Cancel</button>
      </div>
    </div>
  );
}
