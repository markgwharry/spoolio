import React, { useContext, useState } from 'react';
import { AuthContext } from '../../AuthContext';
import { formatGrams } from '../../utils/colorUtils';

export default function SpoolListItem({ spool, onUpdate, onDelete, highlighted, onShowDetail }) {
  const { authFetch } = useContext(AuthContext);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({
    weight_remaining: spool.weight_remaining,
    price: spool.price ?? '',
    notes: spool.notes || '',
    subtype: spool.subtype || '',
    is_active: spool.is_active,
    is_empty: spool.is_empty,
    low_stock_threshold: spool.low_stock_threshold || 100
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [recording, setRecording] = useState(false);
  const [usage, setUsage] = useState('');
  const [projects, setProjects] = useState([]);
  const [selectedProjectId, setSelectedProjectId] = useState('');

  const handleChange = e => {
    const { name, value, type, checked } = e.target;
    setForm(f => ({ ...f, [name]: type === 'checkbox' ? checked : value }));
  };

  const handleSave = async () => {
    setSaving(true);
    setError('');
    try {
      const becameEmpty = !spool.is_empty && !!form.is_empty;
      let returnToPool = true;
      if (becameEmpty) {
        returnToPool = window.confirm('Return this empty spool to the pool for reuse?\nPress OK to return to pool, or Cancel to dispose.');
      }
      const res = await authFetch(`/api/spools/${spool.id}/`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          weight_remaining: parseFloat(form.weight_remaining),
          price: form.price !== '' ? parseFloat(form.price) : null,
          notes: form.notes,
          subtype: form.subtype,
          is_active: form.is_active,
          is_empty: form.is_empty,
          low_stock_threshold: form.low_stock_threshold
        })
      });
      // Check response status before parsing JSON
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        setError(errorData.msg || 'Failed to update spool.');
        setSaving(false);
        return;
      }
      const data = await res.json();
      if (data.spool) {
        // If disposing, remove the auto-created EmptySpool record
        if (becameEmpty && !returnToPool) {
          try {
            const listRes = await authFetch('/api/empty-spools/');
            if (listRes.ok) {
              const list = await listRes.json();
              const toDelete = (list.empty_spools || []).find(e => e.origin_spool_id === data.spool.id);
              if (toDelete) {
                await authFetch(`/api/empty-spools/${toDelete.id}/`, { method: 'DELETE' });
              }
            }
          } catch (e) {}
        }
        onUpdate(data.spool);
        setEditing(false);
      }
    } catch (err) {
      setError('Error connecting to server.');
    }
    setSaving(false);
  };

  const handleDelete = async () => {
    if (!window.confirm('Delete this spool?')) return;
    setSaving(true);
    setError('');
    try {
      const res = await authFetch(`/api/spools/${spool.id}/`, { method: 'DELETE' });
      if (res.ok) {
        onDelete(spool.id);
      } else {
        const data = await res.json();
        setError(data.msg || 'Failed to delete spool.');
      }
    } catch (err) {
      setError('Error connecting to server.');
    }
    setSaving(false);
  };

  const handleRecordUsage = async () => {
    setRecording(true);
    setUsage('');
    setSelectedProjectId('');
    // Fetch projects for dropdown
    try {
      const res = await authFetch('/api/projects/');
      if (res.ok) {
        const data = await res.json();
        setProjects(data.projects || []);
      }
    } catch (e) {}
  };

  const handleUsageSubmit = async e => {
    e.preventDefault();
    setSaving(true);
    setError('');
    const used = parseFloat(usage);
    if (isNaN(used) || used <= 0) {
      setError('Enter a valid amount used.');
      setSaving(false);
      return;
    }
    const newWeight = Math.max(0, (spool.weight_remaining || 0) - used);
    try {
      const becameEmpty = !spool.is_empty && newWeight === 0;
      let returnToPool = true;
      if (becameEmpty) {
        returnToPool = window.confirm('Spool is now empty. Return to pool for reuse?\nPress OK to return to pool, or Cancel to dispose.');
      }
      // Use the /use endpoint which creates history and updates spool
      const res = await authFetch(`/api/spools/${spool.id}/use`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          weight_used: used,
          project_id: selectedProjectId ? parseInt(selectedProjectId) : null
        })
      });
      const data = await res.json();
      if (res.ok) {
        // If disposing, remove the auto-created EmptySpool
        if (becameEmpty && !returnToPool) {
          try {
            const listRes = await authFetch('/api/empty-spools/');
            if (listRes.ok) {
              const list = await listRes.json();
              const toDelete = (list.empty_spools || []).find(e => e.origin_spool_id === data.spool.id);
              if (toDelete) {
                await authFetch(`/api/empty-spools/${toDelete.id}/`, { method: 'DELETE' });
              }
            }
          } catch (e) {}
        }
        onUpdate(data.spool);
        setRecording(false);
        setUsage('');
        setSelectedProjectId('');
      } else {
        setError(data.msg || 'Failed to record usage.');
      }
    } catch (err) {
      setError('Error connecting to server.');
    }
    setSaving(false);
  };

  if (editing) {
    return (
      <div className="spool-detail-card editing">
        <div className="spool-edit-form">
          <div className="edit-row">
            <label>
              <span>Weight (g)</span>
              <input type="number" name="weight_remaining" value={form.weight_remaining} onChange={handleChange} min="0" />
            </label>
            <label>
              <span>Low stock (g)</span>
              <input type="number" name="low_stock_threshold" value={form.low_stock_threshold || 100} onChange={handleChange} min="0" />
            </label>
            <label>
              <span>Price</span>
              <input type="number" name="price" value={form.price} onChange={handleChange} min="0" step="0.01" />
            </label>
          </div>
          <div className="edit-row">
            <label>
              <span>Subtype</span>
              <input name="subtype" value={form.subtype} onChange={handleChange} placeholder="e.g. Matte, Silk" />
            </label>
            <label>
              <span>Notes</span>
              <input name="notes" value={form.notes} onChange={handleChange} placeholder="Storage, batch..." />
            </label>
          </div>
          <div className="edit-row checkboxes">
            <label className="checkbox-label">
              <input type="checkbox" name="is_active" checked={form.is_active} onChange={handleChange} />
              <span>Active</span>
            </label>
            <label className="checkbox-label">
              <input type="checkbox" name="is_empty" checked={form.is_empty} onChange={handleChange} />
              <span>Empty</span>
            </label>
          </div>
          <div className="edit-actions">
            <button type="button" className="btn-primary" onClick={handleSave} disabled={saving}>Save</button>
            <button type="button" className="btn-ghost" onClick={() => setEditing(false)}>Cancel</button>
            <button type="button" className="btn-danger" onClick={handleDelete} disabled={saving}>Delete</button>
          </div>
        </div>
        {error && <div className="spool-detail-error">{error}</div>}
      </div>
    );
  }
  const handleRemoveNfcTag = async () => {
    if (!window.confirm('Remove NFC tag from this spool? This will make the tag appear as orphan when scanned again.')) {
      return;
    }

    setSaving(true);
    setError('');
    try {
      const res = await authFetch(`/api/spools/${spool.id}/`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nfc_tag_id: null })
      });
      const data = await res.json();
      if (res.ok) {
        onUpdate(data.spool);
      } else {
        setError(data.msg || 'Failed to remove NFC tag.');
      }
    } catch (err) {
      setError('Error connecting to server.');
    }
    setSaving(false);
  };

  const isLowStock = spool.weight_remaining <= (spool.low_stock_threshold ?? 100);

  return (
    <div
      id={`spool-item-${spool.id}`}
      className={`spool-detail-card${isLowStock ? ' low-stock' : ''}${highlighted ? ' highlighted' : ''}`}
    >
      <div className="spool-detail-header">
        <div className="spool-detail-weight">{formatGrams(spool.weight_remaining)}g</div>
        <div className="spool-detail-manufacturer">{spool.manufacturer}</div>
      </div>
      <div className="spool-detail-meta">
        <span className="spool-detail-type">{spool.spool_type}</span>
        {spool.subtype && <span className="spool-detail-subtype">{spool.subtype}</span>}
      </div>
      {spool.nfc_tag_id && (
        <div className="spool-detail-nfc">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M2 12C2 6.5 6.5 2 12 2a10 10 0 0 1 8 4"/>
            <path d="M5 12c0-3.9 3.1-7 7-7a7 7 0 0 1 5.7 3"/>
            <circle cx="12" cy="12" r="3"/>
          </svg>
          <span>{spool.nfc_tag_id.slice(0, 8)}...</span>
        </div>
      )}
      {spool.notes && <div className="spool-detail-notes">{spool.notes}</div>}
      <div className="spool-detail-actions">
        <button type="button" className="btn-primary" onClick={handleRecordUsage}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 5v14M5 12h14"/>
          </svg>
          Use
        </button>
        <button type="button" className="btn-ghost" onClick={() => onShowDetail && onShowDetail(spool)}>History</button>
        <button type="button" className="btn-ghost" onClick={() => setEditing(true)}>Edit</button>
        <button type="button" className="btn-danger" onClick={handleDelete}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
          </svg>
        </button>
      </div>
      {spool.nfc_tag_id && (
        <button type="button" className="btn-link remove-nfc" onClick={handleRemoveNfcTag} disabled={saving}>
          Remove NFC
        </button>
      )}
      {recording && (
        <form onSubmit={handleUsageSubmit} className="spool-usage-form expanded">
          <div className="usage-form-row">
            <input
              type="number"
              min="0"
              step="0.1"
              value={usage}
              onChange={e => setUsage(e.target.value)}
              placeholder="Grams used"
              autoFocus
            />
            <select
              value={selectedProjectId}
              onChange={e => setSelectedProjectId(e.target.value)}
              className="project-select"
            >
              <option value="">No project</option>
              {projects.map(p => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
          <div className="usage-form-actions">
            <button type="submit" disabled={saving}>Save</button>
            <button type="button" onClick={() => setRecording(false)}>Cancel</button>
          </div>
        </form>
      )}
      {error && <div className="spool-detail-error">{error}</div>}
    </div>
  );
}
