import React, { useState } from 'react';

const emptyRefillForm = {
  material_id: '',
  color_id: '',
  manufacturer_id: '',
  weight_total: '',
  weight_remaining: '',
  notes: '',
  subtype: '',
  price: '',
};

const emptySpoolForm = {
  spool_type_id: '',
  notes: '',
};

export default function DataEntryForms({
  materials,
  colors,
  manufacturers,
  spoolTypes,
  addRefill,
  addEmptySpool,
  onRefillAdded,
  onEmptySpoolAdded,
  onError,
}) {
  const [refillForm, setRefillForm] = useState(emptyRefillForm);
  const [spoolForm, setSpoolForm] = useState(emptySpoolForm);

  const submitRefill = async () => {
    if (!refillForm.material_id
      || !refillForm.color_id
      || !refillForm.manufacturer_id
      || !refillForm.weight_total) return;

    try {
      const refill = await addRefill({
        material_id: parseInt(refillForm.material_id, 10),
        color_id: parseInt(refillForm.color_id, 10),
        manufacturer_id: parseInt(refillForm.manufacturer_id, 10),
        weight_total: parseFloat(refillForm.weight_total),
        weight_remaining: refillForm.weight_remaining
          ? parseFloat(refillForm.weight_remaining)
          : undefined,
        notes: refillForm.notes || undefined,
        subtype: refillForm.subtype || undefined,
        price: refillForm.price ? parseFloat(refillForm.price) : undefined,
      });
      onRefillAdded(refill);
      setRefillForm(emptyRefillForm);
    } catch (error) {
      onError(error.message || 'Error adding refill');
    }
  };

  const submitEmptySpool = async () => {
    if (!spoolForm.spool_type_id) return;

    try {
      const emptySpool = await addEmptySpool({
        spool_type_id: parseInt(spoolForm.spool_type_id, 10),
        notes: spoolForm.notes || undefined,
      });
      onEmptySpoolAdded(emptySpool);
      setSpoolForm(emptySpoolForm);
    } catch (error) {
      onError(error.message || 'Error adding empty spool');
    }
  };

  return (
    <div style={{ display: 'flex', gap: 24, marginTop: 24 }}>
      <div style={{ flex: 1 }}>
        <h3>Add Refill</h3>
        <div className="card" style={{ padding: 16 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 8 }}>
            <select
              name="material_id"
              value={refillForm.material_id}
              onChange={(event) => setRefillForm({ ...refillForm, material_id: event.target.value })}
            >
              <option value="">Material</option>
              {materials.map((material) => (
                <option key={material.id} value={material.id}>{material.name}</option>
              ))}
            </select>
            <select
              name="color_id"
              value={refillForm.color_id}
              onChange={(event) => setRefillForm({ ...refillForm, color_id: event.target.value })}
            >
              <option value="">Color</option>
              {colors.map((color) => (
                <option key={color.id} value={color.id}>{color.name}</option>
              ))}
            </select>
            <select
              name="manufacturer_id"
              value={refillForm.manufacturer_id}
              onChange={(event) => setRefillForm({ ...refillForm, manufacturer_id: event.target.value })}
            >
              <option value="">Manufacturer</option>
              {manufacturers.map((manufacturer) => (
                <option key={manufacturer.id} value={manufacturer.id}>{manufacturer.name}</option>
              ))}
            </select>
            <input
              type="number"
              min="0"
              name="weight_total"
              placeholder="Total (g)"
              value={refillForm.weight_total}
              onChange={(event) => setRefillForm({ ...refillForm, weight_total: event.target.value })}
            />
            <input
              type="number"
              min="0"
              name="weight_remaining"
              placeholder="Remaining (g)"
              value={refillForm.weight_remaining}
              onChange={(event) => setRefillForm({ ...refillForm, weight_remaining: event.target.value })}
            />
            <input
              name="subtype"
              placeholder="Subtype"
              value={refillForm.subtype}
              onChange={(event) => setRefillForm({ ...refillForm, subtype: event.target.value })}
            />
            <input
              name="notes"
              placeholder="Notes"
              value={refillForm.notes}
              onChange={(event) => setRefillForm({ ...refillForm, notes: event.target.value })}
            />
            <div style={{ gridColumn: '1 / -1', textAlign: 'right' }}>
              <button className="button" type="button" onClick={submitRefill}>Add Refill</button>
            </div>
          </div>
        </div>
      </div>
      <div style={{ flex: 1 }}>
        <h3>Add Empty Spool</h3>
        <div className="card" style={{ padding: 16 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 8 }}>
            <select
              name="spool_type_id"
              value={spoolForm.spool_type_id}
              onChange={(event) => setSpoolForm({ ...spoolForm, spool_type_id: event.target.value })}
            >
              <option value="">Spool Type</option>
              {spoolTypes.map((spoolType) => (
                <option key={spoolType.id} value={spoolType.id}>{spoolType.name}</option>
              ))}
            </select>
            <input
              name="notes"
              placeholder="Notes"
              value={spoolForm.notes}
              onChange={(event) => setSpoolForm({ ...spoolForm, notes: event.target.value })}
            />
            <div style={{ textAlign: 'right' }}>
              <button className="button" type="button" onClick={submitEmptySpool}>Add Empty Spool</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
