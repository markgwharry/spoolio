import React, { useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

const initialForm = {
  material_id: '',
  material_text: '',
  color_id: '',
  color_text: '',
  manufacturer_id: '',
  manufacturer_text: '',
  spool_type_id: '',
  spool_type_text: '',
  spool_type_tare: '',
  weight_start: '',
  weight_remaining: '',
  price: '',
  notes: '',
  subtype: '',
  low_stock_threshold: 100,
};

export default function AddSpoolModal({
  open,
  materials,
  colors,
  manufacturers,
  spoolTypes,
  subtypes,
  mutations,
  onMaterialAdded,
  onColorAdded,
  onManufacturerAdded,
  onSpoolTypeAdded,
  onSpoolAdded,
  onMessage,
  onClose,
}) {
  const [form, setForm] = useState(initialForm);
  const [colorInputMode, setColorInputMode] = useState('select');
  const [manufacturerInputMode, setManufacturerInputMode] = useState('select');
  const [spoolTypeInputMode, setSpoolTypeInputMode] = useState('select');
  const [materialInputMode, setMaterialInputMode] = useState('select');
  const subtypeInputRef = useRef();

  const steps = useMemo(() => ([
    {
      id: 'material',
      label: 'Material & color',
      completed: Boolean(((form.material_id && form.material_id !== '__new__') || form.material_text)
        && ((form.color_id && form.color_id !== '__new__') || form.color_text)),
    },
    {
      id: 'supplier',
      label: 'Supplier & type',
      completed: Boolean(((form.manufacturer_id && form.manufacturer_id !== '__new__') || form.manufacturer_text)
        && ((form.spool_type_id && form.spool_type_id !== '__new__') || form.spool_type_text)),
    },
    {
      id: 'weights',
      label: 'Weights & tracking',
      completed: Boolean(form.weight_start && form.weight_remaining),
    },
  ]), [form]);

  if (!open) return null;

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((current) => ({ ...current, [name]: value }));
    if (name === 'material_id') {
      setForm((current) => ({ ...current, material_text: '' }));
      setMaterialInputMode('select');
    }
    if (name === 'material_text') {
      setForm((current) => ({ ...current, material_id: '' }));
      setMaterialInputMode('text');
    }
    if (name === 'color_id') {
      setForm((current) => ({ ...current, color_text: '' }));
      setColorInputMode('select');
    }
    if (name === 'color_text') {
      setForm((current) => ({ ...current, color_id: '' }));
      setColorInputMode('text');
    }
    if (name === 'manufacturer_id') {
      setForm((current) => ({ ...current, manufacturer_text: '' }));
      setManufacturerInputMode('select');
    }
    if (name === 'manufacturer_text') {
      setForm((current) => ({ ...current, manufacturer_id: '' }));
      setManufacturerInputMode('text');
    }
    if (name === 'spool_type_id') {
      setForm((current) => ({ ...current, spool_type_text: '' }));
      setSpoolTypeInputMode('select');
    }
    if (name === 'spool_type_text') {
      setForm((current) => ({ ...current, spool_type_id: '' }));
      setSpoolTypeInputMode('text');
    }
  };

  const createOnBlur = async ({
    mode,
    text,
    records,
    collection,
    payload,
    onAdded,
    idField,
    setMode,
    errorMessage,
  }) => {
    if (mode !== 'text' || !text?.trim()) return;
    const normalizedName = text.trim();
    const existing = records.find(
      (record) => record.name.toLowerCase() === normalizedName.toLowerCase(),
    );
    if (existing) {
      setForm((current) => ({ ...current, [idField]: existing.id }));
      setMode('select');
      return;
    }

    try {
      const data = await mutations.createMetadata(collection, payload(normalizedName));
      if (data.id) {
        onAdded(data);
        setForm((current) => ({ ...current, [idField]: data.id }));
        setMode('select');
      }
    } catch (error) {
      onMessage(errorMessage);
    }
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    onMessage('');
    let colorId = form.color_id;

    if (colorInputMode === 'text' && form.color_text.trim()) {
      const existing = colors.find(
        (color) => color.name.toLowerCase() === form.color_text.trim().toLowerCase(),
      );
      if (existing) {
        colorId = existing.id;
      } else {
        try {
          const data = await mutations.createMetadata('colors', { name: form.color_text.trim() });
          if (data.id) {
            onColorAdded(data);
            colorId = data.id;
          }
        } catch (error) {
          onMessage('Error adding new color.');
          return;
        }
      }
    }

    try {
      const spool = await mutations.addSpool({
        ...form,
        color_id: colorId,
        weight_start: parseFloat(form.weight_start),
        weight_remaining: parseFloat(form.weight_remaining),
        price: form.price !== '' ? parseFloat(form.price) : null,
        subtype: form.subtype,
      });
      if (spool) {
        onSpoolAdded(spool);
        onMessage('Spool added!');
        onClose();
        setForm(initialForm);
      }
    } catch (error) {
      onMessage(error.message || 'Error connecting to server.');
    }
  };

  return createPortal(
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content spool-form add-spool-modal" onClick={(event) => event.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h3>Add New Spool</h3>
            <p className="form-note">Capture the basics, supplier info, then dial in tracking fields.</p>
          </div>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close modal">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="form-stepper">
          {steps.map((step, index) => (
            <span key={step.id} className={step.completed ? 'completed' : undefined}>
              <span className="step-dot">{index + 1}</span>
              {step.label}
            </span>
          ))}
        </div>
        <form onSubmit={handleSubmit}>
          <div className="form-section">
            <h4>1. Material & color</h4>
            <div className="form-grid compact">
              {materialInputMode === 'select' ? (
                <>
                  <div className="col-6">
                    <label htmlFor="material-select">Material</label>
                    <select id="material-select" name="material_id" value={form.material_id} onChange={handleChange} required>
                      <option value="">Choose material</option>
                      {materials.map((material) => <option key={material.id} value={material.id}>{material.name}</option>)}
                      <option value="__new__">Add new material...</option>
                    </select>
                  </div>
                  {form.material_id === '__new__' && (
                    <div className="col-6">
                      <label htmlFor="material-text">New material name</label>
                      <input
                        id="material-text"
                        name="material_text"
                        placeholder="Enter new material"
                        value={form.material_text}
                        onChange={handleChange}
                        onBlur={() => createOnBlur({
                          mode: materialInputMode,
                          text: form.material_text,
                          records: materials,
                          collection: 'materials',
                          payload: (name) => ({ name }),
                          onAdded: onMaterialAdded,
                          idField: 'material_id',
                          setMode: setMaterialInputMode,
                          errorMessage: 'Error adding new material.',
                        })}
                      />
                    </div>
                  )}
                </>
              ) : (
                <div className="col-6">
                  <label htmlFor="material-text">Material</label>
                  <input
                    id="material-text"
                    name="material_text"
                    placeholder="Enter new material"
                    value={form.material_text}
                    onChange={handleChange}
                    onBlur={() => createOnBlur({
                      mode: materialInputMode,
                      text: form.material_text,
                      records: materials,
                      collection: 'materials',
                      payload: (name) => ({ name }),
                      onAdded: onMaterialAdded,
                      idField: 'material_id',
                      setMode: setMaterialInputMode,
                      errorMessage: 'Error adding new material.',
                    })}
                  />
                </div>
              )}
              {colorInputMode === 'select' ? (
                <>
                  <div className="col-6">
                    <label htmlFor="color-select">Color</label>
                    <select id="color-select" name="color_id" value={form.color_id} onChange={handleChange} required>
                      <option value="">Choose color</option>
                      {colors.map((color) => <option key={color.id} value={color.id}>{color.name}</option>)}
                      <option value="__new__">Add new color...</option>
                    </select>
                  </div>
                  {form.color_id === '__new__' && (
                    <div className="col-6">
                      <label htmlFor="color-text">New color name</label>
                      <input
                        id="color-text"
                        name="color_text"
                        placeholder="Enter new color"
                        value={form.color_text}
                        onChange={handleChange}
                        onBlur={() => createOnBlur({
                          mode: colorInputMode,
                          text: form.color_text,
                          records: colors,
                          collection: 'colors',
                          payload: (name) => ({ name }),
                          onAdded: onColorAdded,
                          idField: 'color_id',
                          setMode: setColorInputMode,
                          errorMessage: 'Error adding new color.',
                        })}
                      />
                    </div>
                  )}
                </>
              ) : (
                <div className="col-6">
                  <label htmlFor="color-text">Color</label>
                  <input
                    id="color-text"
                    name="color_text"
                    placeholder="Enter new color"
                    value={form.color_text}
                    onChange={handleChange}
                    onBlur={() => createOnBlur({
                      mode: colorInputMode,
                      text: form.color_text,
                      records: colors,
                      collection: 'colors',
                      payload: (name) => ({ name }),
                      onAdded: onColorAdded,
                      idField: 'color_id',
                      setMode: setColorInputMode,
                      errorMessage: 'Error adding new color.',
                    })}
                  />
                </div>
              )}
            </div>
          </div>

          <div className="form-section">
            <h4>2. Manufacturer & spool type</h4>
            <div className="form-grid compact">
              {manufacturerInputMode === 'select' ? (
                <>
                  <div className="col-6">
                    <label htmlFor="manufacturer-select">Manufacturer</label>
                    <select id="manufacturer-select" name="manufacturer_id" value={form.manufacturer_id} onChange={handleChange} required>
                      <option value="">Select manufacturer</option>
                      {manufacturers.map((manufacturer) => <option key={manufacturer.id} value={manufacturer.id}>{manufacturer.name}</option>)}
                      <option value="__new__">Add new manufacturer...</option>
                    </select>
                  </div>
                  {form.manufacturer_id === '__new__' && (
                    <div className="col-6">
                      <label htmlFor="manufacturer-text">New manufacturer name</label>
                      <input
                        id="manufacturer-text"
                        name="manufacturer_text"
                        placeholder="Enter new manufacturer"
                        value={form.manufacturer_text}
                        onChange={handleChange}
                        onBlur={() => createOnBlur({
                          mode: manufacturerInputMode,
                          text: form.manufacturer_text,
                          records: manufacturers,
                          collection: 'manufacturers',
                          payload: (name) => ({ name }),
                          onAdded: onManufacturerAdded,
                          idField: 'manufacturer_id',
                          setMode: setManufacturerInputMode,
                          errorMessage: 'Error adding new manufacturer.',
                        })}
                      />
                    </div>
                  )}
                </>
              ) : (
                <div className="col-6">
                  <label htmlFor="manufacturer-text">Manufacturer</label>
                  <input
                    id="manufacturer-text"
                    name="manufacturer_text"
                    placeholder="Enter new manufacturer"
                    value={form.manufacturer_text}
                    onChange={handleChange}
                    onBlur={() => createOnBlur({
                      mode: manufacturerInputMode,
                      text: form.manufacturer_text,
                      records: manufacturers,
                      collection: 'manufacturers',
                      payload: (name) => ({ name }),
                      onAdded: onManufacturerAdded,
                      idField: 'manufacturer_id',
                      setMode: setManufacturerInputMode,
                      errorMessage: 'Error adding new manufacturer.',
                    })}
                  />
                </div>
              )}
              {spoolTypeInputMode === 'select' ? (
                <>
                  <div className="col-6">
                    <label htmlFor="spool-type-select">Spool type</label>
                    <select id="spool-type-select" name="spool_type_id" value={form.spool_type_id} onChange={handleChange} required>
                      <option value="">Select spool type</option>
                      {spoolTypes.map((spoolType) => <option key={spoolType.id} value={spoolType.id}>{spoolType.name}</option>)}
                      <option value="__new__">Add new spool type...</option>
                    </select>
                  </div>
                  {form.spool_type_id === '__new__' && (
                    <div className="col-6">
                      <label htmlFor="spool-type-text">New spool type</label>
                      <input
                        id="spool-type-text"
                        name="spool_type_text"
                        placeholder="Enter new spool type"
                        value={form.spool_type_text}
                        onChange={handleChange}
                        onBlur={() => createOnBlur({
                          mode: spoolTypeInputMode,
                          text: form.spool_type_text,
                          records: spoolTypes,
                          collection: 'spooltypes',
                          payload: (name) => ({
                            name,
                            tare_weight: parseFloat(form.spool_type_tare || 0) || 0,
                          }),
                          onAdded: onSpoolTypeAdded,
                          idField: 'spool_type_id',
                          setMode: setSpoolTypeInputMode,
                          errorMessage: 'Error adding new spool type.',
                        })}
                      />
                    </div>
                  )}
                </>
              ) : (
                <div className="col-6">
                  <label htmlFor="spool-type-text">Spool type</label>
                  <input
                    id="spool-type-text"
                    name="spool_type_text"
                    placeholder="Enter new spool type"
                    value={form.spool_type_text}
                    onChange={handleChange}
                    onBlur={() => createOnBlur({
                      mode: spoolTypeInputMode,
                      text: form.spool_type_text,
                      records: spoolTypes,
                      collection: 'spooltypes',
                      payload: (name) => ({
                        name,
                        tare_weight: parseFloat(form.spool_type_tare || 0) || 0,
                      }),
                      onAdded: onSpoolTypeAdded,
                      idField: 'spool_type_id',
                      setMode: setSpoolTypeInputMode,
                      errorMessage: 'Error adding new spool type.',
                    })}
                  />
                </div>
              )}
              {(spoolTypeInputMode === 'text' || form.spool_type_id === '__new__') && (
                <div className="col-6">
                  <label htmlFor="spool-tare">Empty spool tare (g)</label>
                  <input
                    id="spool-tare"
                    name="spool_type_tare"
                    placeholder="Empty spool tare"
                    value={form.spool_type_tare}
                    onChange={handleChange}
                    type="number"
                    min="0"
                  />
                </div>
              )}
            </div>
          </div>

          <div className="form-section">
            <h4>3. Weights & tracking</h4>
            <div className="form-grid compact">
              <div className="col-3">
                <label htmlFor="weight-start">Start weight (g)</label>
                <input id="weight-start" name="weight_start" value={form.weight_start} onChange={handleChange} required type="number" min="0" />
              </div>
              <div className="col-3">
                <label htmlFor="weight-remaining">Remaining weight (g)</label>
                <input id="weight-remaining" name="weight_remaining" value={form.weight_remaining} onChange={handleChange} required type="number" min="0" />
              </div>
              <div className="col-3">
                <label htmlFor="price">Price (optional)</label>
                <input id="price" name="price" placeholder="19.99" value={form.price} onChange={handleChange} type="number" min="0" step="0.01" />
              </div>
              <div className="col-3">
                <label htmlFor="low-stock">Low stock alert (g)</label>
                <input id="low-stock" name="low_stock_threshold" value={form.low_stock_threshold || 100} onChange={handleChange} type="number" min="0" />
              </div>
              <div className="col-4">
                <label htmlFor="subtype">Subtype (silk, matte, etc.)</label>
                <input
                  id="subtype"
                  name="subtype"
                  placeholder="Subtype"
                  value={form.subtype}
                  onChange={handleChange}
                  list="subtype-list"
                  ref={subtypeInputRef}
                />
                <datalist id="subtype-list">
                  {subtypes.map((subtype, index) => <option key={index} value={subtype} />)}
                </datalist>
              </div>
              <div className="col-8">
                <label htmlFor="notes">Notes</label>
                <input id="notes" name="notes" placeholder="NFC tag, storage notes..." value={form.notes} onChange={handleChange} />
              </div>
            </div>
          </div>

          <div className="modal-footer">
            <button type="button" className="button ghost" onClick={onClose}>Cancel</button>
            <button type="submit" className="button">Add Spool</button>
          </div>
        </form>
      </div>
    </div>,
    document.body,
  );
}
