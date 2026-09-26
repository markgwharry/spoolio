import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
  weight_start: '1000',
  weight_remaining: '1000',
  price: '',
  notes: '',
  subtype: '',
  low_stock_threshold: 100,
};

const focusField = (id) => {
  window.requestAnimationFrame(() => document.getElementById(id)?.focus());
};

function MetadataField({
  id,
  label,
  items,
  idValue,
  textValue,
  isNew,
  isCreating,
  onSelect,
  onTextChange,
  onStartNew,
  onCancelNew,
  onCreate,
  children,
}) {
  if (isNew) {
    return (
      <div className="metadata-create-field col-12">
        <label htmlFor={`${id}-new`}>New {label.toLowerCase()}</label>
        <div className="metadata-create-row">
          <input
            id={`${id}-new`}
            value={textValue}
            onChange={(event) => onTextChange(event.target.value)}
            placeholder={`Enter ${label.toLowerCase()}`}
            autoFocus
          />
          <button
            type="button"
            className="button secondary"
            disabled={isCreating || !textValue.trim()}
            onClick={onCreate}
          >
            {isCreating ? 'Creating…' : 'Create'}
          </button>
          <button type="button" className="button ghost compact" onClick={onCancelNew}>
            Use existing
          </button>
        </div>
        {children}
      </div>
    );
  }

  return (
    <div className="col-6">
      <label htmlFor={id}>{label}</label>
      <select
        id={id}
        value={idValue}
        onChange={(event) => {
          if (event.target.value === '__new__') {
            onStartNew();
          } else {
            onSelect(event.target.value);
          }
        }}
        required
      >
        <option value="">Choose {label.toLowerCase()}</option>
        {items.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        <option value="__new__">Add new {label.toLowerCase()}…</option>
      </select>
    </div>
  );
}

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
  const [currentStep, setCurrentStep] = useState(0);
  const [newFields, setNewFields] = useState({});
  const [creatingField, setCreatingField] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const modalRef = useRef(null);
  const stepHeadingRef = useRef(null);
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  const resetForm = useCallback(() => {
    setForm(initialForm);
    setCurrentStep(0);
    setNewFields({});
    setCreatingField('');
    setSubmitting(false);
  }, []);

  const closeModal = useCallback(() => {
    resetForm();
    onCloseRef.current();
  }, [resetForm]);

  const steps = useMemo(() => ([
    { id: 'material', label: 'Material & colour' },
    { id: 'supplier', label: 'Supplier & type' },
    { id: 'weights', label: 'Weights & tracking' },
  ]), []);

  useEffect(() => {
    if (!open) return undefined;

    const previousActive = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeModal();
        return;
      }

      if (event.key !== 'Tab' || !modalRef.current) return;
      const focusable = [...modalRef.current.querySelectorAll(
        'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])',
      )].filter((element) => !element.hidden && element.offsetParent !== null);
      if (!focusable.length) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    window.requestAnimationFrame(() => modalRef.current?.querySelector('select, input, button')?.focus());

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = previousOverflow;
      previousActive?.focus?.();
    };
  }, [closeModal, open]);

  useEffect(() => {
    if (open) stepHeadingRef.current?.focus();
  }, [currentStep, open]);

  if (!open) return null;

  const updateForm = (name, value) => {
    setForm((current) => ({ ...current, [name]: value }));
  };

  const startNewField = (field) => {
    setNewFields((current) => ({ ...current, [field]: true }));
    updateForm(`${field}_id`, '');
  };

  const cancelNewField = (field) => {
    setNewFields((current) => ({ ...current, [field]: false }));
    setForm((current) => ({ ...current, [`${field}_text`]: '' }));
  };

  const metadata = {
    material: {
      records: materials,
      collection: 'materials',
      onAdded: onMaterialAdded,
      payload: (name) => ({ name }),
      label: 'material',
    },
    color: {
      records: colors,
      collection: 'colors',
      onAdded: onColorAdded,
      payload: (name) => ({ name }),
      label: 'colour',
    },
    manufacturer: {
      records: manufacturers,
      collection: 'manufacturers',
      onAdded: onManufacturerAdded,
      payload: (name) => ({ name }),
      label: 'manufacturer',
    },
    spool_type: {
      records: spoolTypes,
      collection: 'spooltypes',
      onAdded: onSpoolTypeAdded,
      payload: (name) => ({
        name,
        tare_weight: Number.parseFloat(form.spool_type_tare || 0) || 0,
      }),
      label: 'spool type',
    },
  };

  const createMetadataValue = async (field) => {
    const config = metadata[field];
    const name = form[`${field}_text`]?.trim();
    if (!name) return;

    const existing = config.records.find((record) => record.name.toLowerCase() === name.toLowerCase());
    if (existing) {
      setForm((current) => ({
        ...current,
        [`${field}_id`]: existing.id,
        [`${field}_text`]: '',
      }));
      setNewFields((current) => ({ ...current, [field]: false }));
      onMessage(`${existing.name} was already available, so it has been selected.`);
      return;
    }

    setCreatingField(field);
    onMessage('');
    try {
      const created = await mutations.createMetadata(config.collection, config.payload(name));
      if (!created?.id) throw new Error(`Could not create ${config.label}.`);
      config.onAdded(created);
      setForm((current) => ({
        ...current,
        [`${field}_id`]: created.id,
        [`${field}_text`]: '',
      }));
      setNewFields((current) => ({ ...current, [field]: false }));
      onMessage(`${created.name || name} created and selected.`);
    } catch (error) {
      onMessage(error.message || `Error adding new ${config.label}.`);
    } finally {
      setCreatingField('');
    }
  };

  const fieldProps = (field, id, label, items) => ({
    id,
    label,
    items,
    idValue: form[`${field}_id`],
    textValue: form[`${field}_text`],
    isNew: Boolean(newFields[field]),
    isCreating: creatingField === field,
    onSelect: (value) => updateForm(`${field}_id`, value),
    onTextChange: (value) => updateForm(`${field}_text`, value),
    onStartNew: () => startNewField(field),
    onCancelNew: () => cancelNewField(field),
    onCreate: () => createMetadataValue(field),
  });

  const validateStep = () => {
    if (currentStep === 0) {
      if (newFields.material || !form.material_id) {
        onMessage('Choose or create a material to continue.');
        focusField(newFields.material ? 'material-select-new' : 'material-select');
        return false;
      }
      if (newFields.color || !form.color_id) {
        onMessage('Choose or create a colour to continue.');
        focusField(newFields.color ? 'color-select-new' : 'color-select');
        return false;
      }
    }

    if (currentStep === 1) {
      if (newFields.manufacturer || !form.manufacturer_id) {
        onMessage('Choose or create a manufacturer to continue.');
        focusField(newFields.manufacturer ? 'manufacturer-select-new' : 'manufacturer-select');
        return false;
      }
      if (newFields.spool_type || !form.spool_type_id) {
        onMessage('Choose or create a spool type to continue.');
        focusField(newFields.spool_type ? 'spool-type-select-new' : 'spool-type-select');
        return false;
      }
    }

    if (currentStep === 2) {
      const startWeight = Number.parseFloat(form.weight_start);
      const remainingWeight = Number.parseFloat(form.weight_remaining);
      if (!Number.isFinite(startWeight) || startWeight < 0) {
        onMessage('Enter a valid starting weight.');
        focusField('weight-start');
        return false;
      }
      if (!Number.isFinite(remainingWeight) || remainingWeight < 0) {
        onMessage('Enter a valid remaining weight.');
        focusField('weight-remaining');
        return false;
      }
      if (remainingWeight > startWeight) {
        onMessage('Remaining weight cannot be greater than starting weight.');
        focusField('weight-remaining');
        return false;
      }
    }

    onMessage('');
    return true;
  };

  const goNext = () => {
    if (!validateStep()) return;
    setCurrentStep((step) => Math.min(step + 1, steps.length - 1));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (currentStep < steps.length - 1) {
      goNext();
      return;
    }
    if (!validateStep()) return;

    setSubmitting(true);
    try {
      const spool = await mutations.addSpool({
        ...form,
        weight_start: Number.parseFloat(form.weight_start),
        weight_remaining: Number.parseFloat(form.weight_remaining),
        low_stock_threshold: Number.parseFloat(form.low_stock_threshold || 0),
        price: form.price !== '' ? Number.parseFloat(form.price) : null,
      });
      if (spool) {
        onSpoolAdded(spool);
        onMessage('Spool added.');
        resetForm();
        onClose();
      }
    } catch (error) {
      onMessage(error.message || 'Error connecting to server.');
    } finally {
      setSubmitting(false);
    }
  };

  return createPortal(
    <div
      className="modal-overlay"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) closeModal();
      }}
    >
      <div
        ref={modalRef}
        className="modal-content spool-form add-spool-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-spool-title"
      >
        <div className="modal-header">
          <div>
            <h3 id="add-spool-title">Add a spool</h3>
            <p className="form-note">Three short steps. You can add a missing option without losing your place.</p>
          </div>
          <button type="button" className="modal-close" onClick={closeModal} aria-label="Close add spool">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        <ol className="form-stepper" aria-label="Add spool progress">
          {steps.map((step, index) => (
            <li
              key={step.id}
              className={`${index < currentStep ? 'completed' : ''} ${index === currentStep ? 'current' : ''}`.trim()}
              aria-current={index === currentStep ? 'step' : undefined}
            >
              <span className="step-dot" aria-hidden="true">{index < currentStep ? '✓' : index + 1}</span>
              <span>{step.label}</span>
            </li>
          ))}
        </ol>

        <form onSubmit={handleSubmit} noValidate>
          <div className="wizard-body">
            {currentStep === 0 && (
              <section className="form-section wizard-step" aria-labelledby="material-step-title">
                <p className="eyebrow">Step 1 of 3</p>
                <h4 id="material-step-title" ref={stepHeadingRef} tabIndex="-1">What is it?</h4>
                <p className="form-note">Choose the material and colour you will look for on the shelf.</p>
                <div className="form-grid compact">
                  <MetadataField {...fieldProps('material', 'material-select', 'Material', materials)} />
                  <MetadataField {...fieldProps('color', 'color-select', 'Colour', colors)} />
                </div>
              </section>
            )}

            {currentStep === 1 && (
              <section className="form-section wizard-step" aria-labelledby="supplier-step-title">
                <p className="eyebrow">Step 2 of 3</p>
                <h4 id="supplier-step-title" ref={stepHeadingRef} tabIndex="-1">Who made the spool?</h4>
                <p className="form-note">The spool type supplies the empty-spool tare used by weight tracking.</p>
                <div className="form-grid compact">
                  <MetadataField {...fieldProps('manufacturer', 'manufacturer-select', 'Manufacturer', manufacturers)} />
                  <MetadataField {...fieldProps('spool_type', 'spool-type-select', 'Spool type', spoolTypes)}>
                    <div className="new-spool-tare">
                      <label htmlFor="spool-tare">Empty spool tare (g)</label>
                      <input
                        id="spool-tare"
                        value={form.spool_type_tare}
                        onChange={(event) => updateForm('spool_type_tare', event.target.value)}
                        type="number"
                        min="0"
                        inputMode="decimal"
                        placeholder="e.g. 250"
                      />
                    </div>
                  </MetadataField>
                </div>
              </section>
            )}

            {currentStep === 2 && (
              <section className="form-section wizard-step" aria-labelledby="weight-step-title">
                <p className="eyebrow">Step 3 of 3</p>
                <h4 id="weight-step-title" ref={stepHeadingRef} tabIndex="-1">How much filament is left?</h4>
                <p className="form-note">A new 1 kg spool usually starts and remains at 1000 g.</p>
                <div className="form-grid compact">
                  <div className="col-6">
                    <label htmlFor="weight-start">Starting filament weight (g)</label>
                    <input
                      id="weight-start"
                      value={form.weight_start}
                      onChange={(event) => updateForm('weight_start', event.target.value)}
                      type="number"
                      min="0"
                      inputMode="decimal"
                      required
                    />
                  </div>
                  <div className="col-6">
                    <label htmlFor="weight-remaining">Remaining filament (g)</label>
                    <input
                      id="weight-remaining"
                      value={form.weight_remaining}
                      onChange={(event) => updateForm('weight_remaining', event.target.value)}
                      type="number"
                      min="0"
                      inputMode="decimal"
                      required
                    />
                  </div>
                </div>

                <details className="advanced-fields">
                  <summary>Optional details</summary>
                  <div className="form-grid compact">
                    <div className="col-6">
                      <label htmlFor="price">Price</label>
                      <input id="price" value={form.price} onChange={(event) => updateForm('price', event.target.value)} type="number" min="0" step="0.01" placeholder="19.99" />
                    </div>
                    <div className="col-6">
                      <label htmlFor="low-stock">Low-stock alert (g)</label>
                      <input id="low-stock" value={form.low_stock_threshold} onChange={(event) => updateForm('low_stock_threshold', event.target.value)} type="number" min="0" />
                    </div>
                    <div className="col-6">
                      <label htmlFor="subtype">Finish or subtype</label>
                      <input id="subtype" value={form.subtype} onChange={(event) => updateForm('subtype', event.target.value)} list="subtype-list" placeholder="Matte, silk, carbon fibre…" />
                      <datalist id="subtype-list">
                        {subtypes.map((subtype) => <option key={subtype} value={subtype} />)}
                      </datalist>
                    </div>
                    <div className="col-6">
                      <label htmlFor="notes">Notes</label>
                      <input id="notes" value={form.notes} onChange={(event) => updateForm('notes', event.target.value)} placeholder="Storage, NFC tag, print profile…" />
                    </div>
                  </div>
                </details>
              </section>
            )}
          </div>

          <div className="modal-footer wizard-footer">
            <button type="button" className="button ghost" onClick={currentStep === 0 ? closeModal : () => setCurrentStep((step) => step - 1)}>
              {currentStep === 0 ? 'Cancel' : 'Back'}
            </button>
            <button type="submit" className="button" disabled={submitting || Boolean(creatingField)}>
              {currentStep < steps.length - 1 ? 'Continue' : (submitting ? 'Adding spool…' : 'Add spool')}
            </button>
          </div>
        </form>
      </div>
    </div>,
    document.body,
  );
}
