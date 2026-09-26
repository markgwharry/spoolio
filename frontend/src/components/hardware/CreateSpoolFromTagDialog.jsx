import React, { useEffect, useMemo, useState } from 'react';

const TAG_FORMAT_LABELS = { bambu: 'Bambu Lab' };

export function tagFormatLabel(format) {
  return TAG_FORMAT_LABELS[format] || format;
}

// Compact description of what a device decoded from an orphan tag.
export function TagSummary({ orphan }) {
  const meta = orphan?.tag_metadata;
  if (!meta) return null;
  const name = meta.variant || meta.material;
  return (
    <span className="tag-summary">
      <span className="tag-format-badge">{tagFormatLabel(meta.format)}</span>
      {meta.color_hex && (
        <span
          className="tag-color-swatch"
          style={{ backgroundColor: meta.color_hex }}
          title={meta.color_hex}
          aria-hidden="true"
        />
      )}
      {name && <span>{name}</span>}
      {meta.spool_weight ? <span className="tag-summary-muted">{meta.spool_weight} g</span> : null}
    </span>
  );
}

function defaultSpoolTypeId(spoolTypes, format) {
  if (!spoolTypes?.length) return '';
  if (format) {
    const match = spoolTypes.find(type => type.name?.toLowerCase().includes(format.toLowerCase()));
    if (match) return String(match.id);
  }
  return String(spoolTypes[0].id);
}

function NameList({ id, items }) {
  return (
    <datalist id={id}>
      {(items || []).map(item => <option key={item.id} value={item.name} />)}
    </datalist>
  );
}

export default function CreateSpoolFromTagDialog({
  orphan,
  authFetch,
  spoolTypes,
  materials,
  colors,
  manufacturers,
  onCancel,
  onCreated,
}) {
  const suggestions = useMemo(() => orphan?.suggestions || {}, [orphan]);
  const meta = orphan?.tag_metadata || {};
  const [form, setForm] = useState(() => ({
    material: suggestions.material || '',
    subtype: suggestions.subtype || '',
    color: suggestions.color || '',
    manufacturer: suggestions.manufacturer || '',
    weight_start: suggestions.weight_start ? String(suggestions.weight_start) : '1000',
    spool_type_id: defaultSpoolTypeId(spoolTypes, meta.format),
  }));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    // Spool types can arrive after the dialog opens.
    if (!form.spool_type_id && spoolTypes?.length) {
      setForm(current => ({ ...current, spool_type_id: defaultSpoolTypeId(spoolTypes, meta.format) }));
    }
  }, [spoolTypes, form.spool_type_id, meta.format]);

  useEffect(() => {
    const onKeyDown = (event) => {
      if (event.key === 'Escape') onCancel();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [onCancel]);

  const update = (field) => (event) => setForm(current => ({ ...current, [field]: event.target.value }));

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const res = await authFetch('/api/hardware/orphans/create-spool', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          nfc_tag_id: orphan.nfc_tag_id,
          material: form.material,
          subtype: form.subtype,
          color: form.color,
          manufacturer: form.manufacturer,
          weight_start: Number(form.weight_start),
          spool_type_id: Number(form.spool_type_id),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || 'Failed to create spool');
      onCreated(data.spool);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="register-form-overlay"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onCancel();
      }}
    >
      <div className="register-form" role="dialog" aria-modal="true" aria-labelledby="create-spool-from-tag-title">
        <h3 id="create-spool-from-tag-title">Create spool from tag</h3>
        <p className="tag-dialog-intro">
          <TagSummary orphan={orphan} />
        </p>
        {meta.color_hex && (
          <p className="tag-dialog-hint">
            The tag stores colour {meta.color_hex}, not a name. Check the suggested name
            {meta.variant_id ? ` (Bambu code ${meta.variant_id})` : ''}.
          </p>
        )}
        {error && <div className="error-message" role="alert">{error}</div>}
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="tag-material">Material</label>
            <input id="tag-material" list="tag-material-options" value={form.material} onChange={update('material')} required />
            <NameList id="tag-material-options" items={materials} />
          </div>
          <div className="form-group">
            <label htmlFor="tag-subtype">Subtype</label>
            <input id="tag-subtype" value={form.subtype} onChange={update('subtype')} placeholder="e.g. Basic, Matte" />
          </div>
          <div className="form-group">
            <label htmlFor="tag-color">Colour name</label>
            <input id="tag-color" list="tag-color-options" value={form.color} onChange={update('color')} required />
            <NameList id="tag-color-options" items={colors} />
          </div>
          <div className="form-group">
            <label htmlFor="tag-manufacturer">Manufacturer</label>
            <input id="tag-manufacturer" list="tag-manufacturer-options" value={form.manufacturer} onChange={update('manufacturer')} required />
            <NameList id="tag-manufacturer-options" items={manufacturers} />
          </div>
          <div className="form-group">
            <label htmlFor="tag-weight">Filament weight when full (g)</label>
            <input id="tag-weight" type="number" min="1" step="1" value={form.weight_start} onChange={update('weight_start')} required />
          </div>
          <div className="form-group">
            <label htmlFor="tag-spool-type">Spool type</label>
            <select id="tag-spool-type" value={form.spool_type_id} onChange={update('spool_type_id')} required>
              <option value="" disabled>Select spool type…</option>
              {(spoolTypes || []).map(type => (
                <option key={type.id} value={type.id}>{type.name}</option>
              ))}
            </select>
            <small>Its empty weight is subtracted from the last reading to set what's left.</small>
          </div>
          <div className="form-actions">
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? 'Creating…' : 'Create spool'}
            </button>
            <button type="button" className="btn btn-secondary" onClick={onCancel}>Cancel</button>
          </div>
        </form>
      </div>
    </div>
  );
}
