import React, { useContext, useEffect, useState, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { AuthContext } from './AuthContext';
import SpoolSpinner from './components/SpoolSpinner';
import EmptyState from './components/EmptyState';
import useMetadata, { BITS_METADATA } from './hooks/useMetadata';

export default function BitsInventory() {
  const { authFetch } = useContext(AuthContext);
  const [bits, setBits] = useState([]);
  const metadata = useMetadata(authFetch, BITS_METADATA);
  const categories = metadata.bitCategories;
  const reloadMetadata = metadata.reload;
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  // Filters & sort
  const [filterCategoryId, setFilterCategoryId] = useState('');
  const [filterLowStockOnly, setFilterLowStockOnly] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [sortMode, setSortMode] = useState('category');

  // Modals
  const [showAddModal, setShowAddModal] = useState(false);
  const [showUseModal, setShowUseModal] = useState(null); // bit object
  const [showRestockModal, setShowRestockModal] = useState(null); // bit object
  const [editingBit, setEditingBit] = useState(null);

  // Add form
  const [form, setForm] = useState({
    category_id: '',
    category_text: '',
    name: '',
    description: '',
    quantity_total: '',
    unit: 'pcs',
    price: '',
    supplier: '',
    purchase_date: '',
    notes: '',
    low_stock_threshold: 10,
  });
  const [categoryInputMode, setCategoryInputMode] = useState('select');

  // Use form
  const [useForm, setUseForm] = useState({ quantity_used: '', project_id: '', notes: '' });

  // Restock form
  const [restockForm, setRestockForm] = useState({ quantity: '', price: '', supplier: '', purchase_date: '' });

  // --- Data loading ---
  useEffect(() => {
    async function fetchData() {
      setLoading(true);
      try {
        const [bitsRes, projRes] = await Promise.all([
          authFetch('/api/bits/'),
          authFetch('/api/projects/'),
          reloadMetadata().catch(() => null),
        ]);
        if (bitsRes.ok) {
          const d = await bitsRes.json();
          setBits(Array.isArray(d.bits) ? d.bits : []);
        } else {
          setError('Failed to load bits');
        }
        if (projRes.ok) {
          const d = await projRes.json();
          setProjects(Array.isArray(d.projects) ? d.projects : []);
        }
      } catch (e) {
        setError('Error connecting to server');
      }
      setLoading(false);
    }
    fetchData();
  }, [authFetch, reloadMetadata]);

  // --- Filtering & sorting ---
  const filteredBits = useMemo(() => {
    let result = [...bits];
    if (filterCategoryId) {
      result = result.filter(b => String(b.category_id) === String(filterCategoryId));
    }
    if (filterLowStockOnly) {
      result = result.filter(b => b.quantity_remaining <= (b.low_stock_threshold || 0));
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(b =>
        b.name.toLowerCase().includes(q) ||
        (b.supplier || '').toLowerCase().includes(q) ||
        (b.description || '').toLowerCase().includes(q)
      );
    }
    // Sort
    result.sort((a, b) => {
      if (sortMode === 'alpha') return a.name.localeCompare(b.name);
      if (sortMode === 'quantity-desc') return b.quantity_remaining - a.quantity_remaining;
      if (sortMode === 'quantity-asc') return a.quantity_remaining - b.quantity_remaining;
      if (sortMode === 'low-stock') {
        const aLow = a.quantity_remaining <= (a.low_stock_threshold || 0) ? 0 : 1;
        const bLow = b.quantity_remaining <= (b.low_stock_threshold || 0) ? 0 : 1;
        if (aLow !== bLow) return aLow - bLow;
        return a.name.localeCompare(b.name);
      }
      // default: category
      const catCmp = (a.category_name || '').localeCompare(b.category_name || '');
      return catCmp !== 0 ? catCmp : a.name.localeCompare(b.name);
    });
    return result;
  }, [bits, filterCategoryId, filterLowStockOnly, searchQuery, sortMode]);

  // Group by category for display
  const grouped = useMemo(() => {
    const groups = {};
    for (const b of filteredBits) {
      const cat = b.category_name || 'Uncategorized';
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(b);
    }
    return groups;
  }, [filteredBits]);

  // --- Stats ---
  const stats = useMemo(() => {
    const total = bits.length;
    const totalQty = bits.reduce((s, b) => s + (b.quantity_remaining || 0), 0);
    const lowStock = bits.filter(b => b.quantity_remaining <= (b.low_stock_threshold || 0)).length;
    const totalValue = bits.reduce((s, b) => {
      if (b.price && b.quantity_total > 0) {
        return s + (b.price / b.quantity_total) * b.quantity_remaining;
      }
      return s;
    }, 0);
    return { total, totalQty, lowStock, totalValue };
  }, [bits]);

  // --- Handlers ---

  const handleAddBit = async (e) => {
    e.preventDefault();
    setMessage('');

    let category_id = form.category_id;
    if (categoryInputMode === 'text' && form.category_text.trim()) {
      try {
        const res = await authFetch('/api/bitcategories/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: form.category_text.trim() })
        });
        const data = await res.json();
        if (res.ok && data.id) {
          metadata.setCollection('bitCategories', cs => {
            if (cs.find(c => c.id === data.id)) return cs;
            return [...cs, { id: data.id, name: data.name }];
          });
          category_id = data.id;
        } else {
          setMessage('Error creating category');
          return;
        }
      } catch {
        setMessage('Error creating category');
        return;
      }
    }

    if (!category_id || !form.name.trim() || !form.quantity_total) {
      setMessage('Category, name, and quantity are required');
      return;
    }

    try {
      const res = await authFetch('/api/bits/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          category_id: parseInt(category_id),
          name: form.name.trim(),
          description: form.description.trim() || null,
          quantity_total: parseInt(form.quantity_total),
          unit: form.unit || 'pcs',
          price: form.price ? parseFloat(form.price) : null,
          supplier: form.supplier.trim() || null,
          purchase_date: form.purchase_date || null,
          notes: form.notes.trim() || null,
          low_stock_threshold: parseInt(form.low_stock_threshold) || 10,
        })
      });
      const data = await res.json();
      if (res.ok) {
        setBits(prev => [...prev, data.bit]);
        setMessage('Bit added!');
        setShowAddModal(false);
        setForm({ category_id: '', category_text: '', name: '', description: '', quantity_total: '', unit: 'pcs', price: '', supplier: '', purchase_date: '', notes: '', low_stock_threshold: 10 });
      } else {
        setMessage(data.msg || 'Failed to add bit');
      }
    } catch {
      setMessage('Error connecting to server');
    }
  };

  const handleUseBit = async (e) => {
    e.preventDefault();
    if (!showUseModal) return;
    const qty = parseInt(useForm.quantity_used);
    if (!qty || qty <= 0) { setMessage('Enter a valid quantity'); return; }

    try {
      const res = await authFetch(`/api/bits/${showUseModal.id}/use`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          quantity_used: qty,
          project_id: useForm.project_id ? parseInt(useForm.project_id) : null,
          notes: useForm.notes.trim() || null,
        })
      });
      const data = await res.json();
      if (res.ok) {
        setBits(prev => prev.map(b => b.id === data.bit.id ? data.bit : b));
        setMessage(`Used ${qty} ${showUseModal.unit}`);
        setShowUseModal(null);
        setUseForm({ quantity_used: '', project_id: '', notes: '' });
      } else {
        setMessage(data.msg || 'Failed to record usage');
      }
    } catch {
      setMessage('Error connecting to server');
    }
  };

  const handleRestock = async (e) => {
    e.preventDefault();
    if (!showRestockModal) return;
    const qty = parseInt(restockForm.quantity);
    if (!qty || qty <= 0) { setMessage('Enter a valid quantity'); return; }

    try {
      const res = await authFetch(`/api/bits/${showRestockModal.id}/restock`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          quantity: qty,
          price: restockForm.price ? parseFloat(restockForm.price) : null,
          supplier: restockForm.supplier.trim() || null,
          purchase_date: restockForm.purchase_date || null,
        })
      });
      const data = await res.json();
      if (res.ok) {
        setBits(prev => prev.map(b => b.id === data.bit.id ? data.bit : b));
        setMessage(`Restocked ${qty} ${showRestockModal.unit}`);
        setShowRestockModal(null);
        setRestockForm({ quantity: '', price: '', supplier: '', purchase_date: '' });
      } else {
        setMessage(data.msg || 'Failed to restock');
      }
    } catch {
      setMessage('Error connecting to server');
    }
  };

  const handleDeleteBit = async (bit) => {
    if (!window.confirm(`Delete "${bit.name}"? This will also remove all usage history.`)) return;
    try {
      const res = await authFetch(`/api/bits/${bit.id}/`, { method: 'DELETE' });
      if (res.ok) {
        setBits(prev => prev.filter(b => b.id !== bit.id));
        setMessage('Bit deleted');
      } else {
        const data = await res.json();
        setMessage(data.msg || 'Failed to delete');
      }
    } catch {
      setMessage('Error connecting to server');
    }
  };

  const handleUpdateBit = async (e) => {
    e.preventDefault();
    if (!editingBit) return;
    try {
      const res = await authFetch(`/api/bits/${editingBit.id}/`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: editingBit.name,
          description: editingBit.description || null,
          category_id: editingBit.category_id,
          quantity_remaining: parseInt(editingBit.quantity_remaining),
          quantity_total: parseInt(editingBit.quantity_total),
          low_stock_threshold: parseInt(editingBit.low_stock_threshold) || 10,
          unit: editingBit.unit,
          price: editingBit.price ? parseFloat(editingBit.price) : null,
          supplier: editingBit.supplier || null,
          notes: editingBit.notes || null,
        })
      });
      const data = await res.json();
      if (res.ok) {
        setBits(prev => prev.map(b => b.id === data.bit.id ? data.bit : b));
        setMessage('Bit updated');
        setEditingBit(null);
      } else {
        setMessage(data.msg || 'Failed to update');
      }
    } catch {
      setMessage('Error connecting to server');
    }
  };

  // --- Render ---

  if (loading) return <div className="page-loading"><SpoolSpinner label="Loading bits…" /></div>;
  if (error) return <div className="error-banner">{error}</div>;

  const stockPct = (b) => b.quantity_total > 0 ? Math.round((b.quantity_remaining / b.quantity_total) * 100) : 0;
  const isLow = (b) => b.quantity_remaining <= (b.low_stock_threshold || 0);

  return (
    <div style={{ maxWidth: 960, margin: '0 auto', padding: '1.5rem 1rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '0.75rem' }}>
        <h1 style={{ margin: 0, fontSize: '1.5rem' }}>Bits Inventory</h1>
        <button onClick={() => setShowAddModal(true)} style={btnStyle}>+ Add Bit</button>
      </div>

      {message && (
        <div style={{ padding: '0.5rem 1rem', marginBottom: '1rem', borderRadius: 6, background: 'var(--color-surface-alt, #2a2a2a)', border: '1px solid var(--color-border, #444)' }}>
          {message}
          <button onClick={() => setMessage('')} style={{ marginLeft: 8, background: 'none', border: 'none', color: 'inherit', cursor: 'pointer' }}>x</button>
        </div>
      )}

      {/* Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '0.75rem', marginBottom: '1.5rem' }}>
        <StatCard label="Total Items" value={stats.total} />
        <StatCard label="Total Quantity" value={stats.totalQty.toLocaleString()} />
        <StatCard label="Low Stock" value={stats.lowStock} accent={stats.lowStock > 0} />
        <StatCard label="Est. Value" value={`£${stats.totalValue.toFixed(2)}`} />
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '1rem', alignItems: 'center' }}>
        <input
          type="text"
          placeholder="Search bits..."
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
          style={inputStyle}
        />
        <select value={filterCategoryId} onChange={e => setFilterCategoryId(e.target.value)} style={inputStyle}>
          <option value="">All categories</option>
          {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select value={sortMode} onChange={e => setSortMode(e.target.value)} style={inputStyle}>
          <option value="category">Sort: Category</option>
          <option value="alpha">Sort: A-Z</option>
          <option value="quantity-desc">Sort: Qty High-Low</option>
          <option value="quantity-asc">Sort: Qty Low-High</option>
          <option value="low-stock">Sort: Low Stock First</option>
        </select>
        <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.85rem', cursor: 'pointer' }}>
          <input type="checkbox" checked={filterLowStockOnly} onChange={e => setFilterLowStockOnly(e.target.checked)} />
          Low stock only
        </label>
      </div>

      {/* Grouped list */}
      {filteredBits.length === 0 ? (
        bits.length === 0 ? (
          <EmptyState
            title="No parts yet"
            message="Add your first hardware component to start tracking stock."
          />
        ) : (
          <EmptyState
            title="No parts match your filters"
            message="Try clearing a filter to see more."
          />
        )
      ) : (
        Object.entries(grouped).map(([catName, catBits]) => (
          <div key={catName} style={{ marginBottom: '1.5rem' }}>
            <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.5rem', borderBottom: '1px solid var(--color-border, #444)', paddingBottom: '0.35rem' }}>{catName}</h2>
            <div style={{ display: 'grid', gap: '0.5rem' }}>
              {catBits.map(bit => (
                <div key={bit.id} style={cardStyle}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.75rem', flexWrap: 'wrap' }}>
                    <div style={{ flex: 1, minWidth: 180 }}>
                      <div style={{ fontWeight: 600, fontSize: '0.95rem' }}>{bit.name}</div>
                      {bit.description && <div style={{ fontSize: '0.8rem', opacity: 0.7, marginTop: 2 }}>{bit.description}</div>}
                      <div style={{ fontSize: '0.8rem', opacity: 0.6, marginTop: 4, display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
                        {bit.supplier && <span>Supplier: {bit.supplier}</span>}
                        {bit.price != null && <span>Price: £{Number(bit.price).toFixed(2)}</span>}
                        {bit.unit !== 'pcs' && <span>Unit: {bit.unit}</span>}
                      </div>
                    </div>
                    <div style={{ textAlign: 'right', minWidth: 120 }}>
                      <div style={{ fontSize: '1.1rem', fontWeight: 700 }}>
                        <span style={{ color: isLow(bit) ? 'var(--color-warning, #e8a735)' : 'inherit' }}>
                          {bit.quantity_remaining}
                        </span>
                        <span style={{ opacity: 0.5, fontWeight: 400 }}> / {bit.quantity_total} {bit.unit}</span>
                      </div>
                      {/* Stock bar */}
                      <div style={{ height: 4, background: 'var(--color-surface-alt, #333)', borderRadius: 2, marginTop: 4, overflow: 'hidden' }}>
                        <div style={{
                          height: '100%',
                          width: `${stockPct(bit)}%`,
                          background: isLow(bit) ? 'var(--color-warning, #e8a735)' : 'var(--color-accent, #5ba85b)',
                          borderRadius: 2,
                          transition: 'width 0.3s',
                        }} />
                      </div>
                      {isLow(bit) && <div style={{ fontSize: '0.7rem', color: 'var(--color-warning, #e8a735)', marginTop: 2 }}>Low stock</div>}
                    </div>
                  </div>
                  {/* Actions */}
                  <div style={{ display: 'flex', gap: '0.4rem', marginTop: '0.5rem', flexWrap: 'wrap' }}>
                    <button onClick={() => { setShowUseModal(bit); setUseForm({ quantity_used: '', project_id: '', notes: '' }); }} style={smallBtnStyle}>Use</button>
                    <button onClick={() => { setShowRestockModal(bit); setRestockForm({ quantity: '', price: '', supplier: bit.supplier || '', purchase_date: '' }); }} style={smallBtnStyle}>Restock</button>
                    <button onClick={() => setEditingBit({ ...bit })} style={smallBtnStyle}>Edit</button>
                    <button onClick={() => handleDeleteBit(bit)} style={{ ...smallBtnStyle, color: 'var(--color-danger, #d9534f)' }}>Delete</button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))
      )}

      {/* --- Modals --- */}

      {/* Add Bit Modal */}
      {showAddModal && createPortal(
        <Overlay onClose={() => setShowAddModal(false)}>
          <h2 style={{ marginTop: 0, fontSize: '1.2rem' }}>Add Bit</h2>
          <form onSubmit={handleAddBit}>
            <div style={{ marginBottom: 8 }}>
              <label style={labelStyle}>Category</label>
              <div style={{ display: 'flex', gap: 4, marginBottom: 4 }}>
                <button type="button" onClick={() => setCategoryInputMode('select')} style={{ ...tabBtnStyle, fontWeight: categoryInputMode === 'select' ? 700 : 400 }}>Select</button>
                <button type="button" onClick={() => setCategoryInputMode('text')} style={{ ...tabBtnStyle, fontWeight: categoryInputMode === 'text' ? 700 : 400 }}>New</button>
              </div>
              {categoryInputMode === 'select' ? (
                <select value={form.category_id} onChange={e => setForm(f => ({ ...f, category_id: e.target.value }))} style={inputStyle} required>
                  <option value="">Select category...</option>
                  {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              ) : (
                <input type="text" placeholder="New category name" value={form.category_text} onChange={e => setForm(f => ({ ...f, category_text: e.target.value }))} style={inputStyle} required />
              )}
            </div>
            <div style={{ marginBottom: 8 }}>
              <label style={labelStyle}>Name *</label>
              <input type="text" placeholder="e.g. M3x8 Socket Head Cap Screw" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} style={inputStyle} required />
            </div>
            <div style={{ marginBottom: 8 }}>
              <label style={labelStyle}>Description</label>
              <input type="text" placeholder="Optional details or specs" value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} style={inputStyle} />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 8 }}>
              <div>
                <label style={labelStyle}>Quantity *</label>
                <input type="number" min="1" value={form.quantity_total} onChange={e => setForm(f => ({ ...f, quantity_total: e.target.value }))} style={inputStyle} required />
              </div>
              <div>
                <label style={labelStyle}>Unit</label>
                <select value={form.unit} onChange={e => setForm(f => ({ ...f, unit: e.target.value }))} style={inputStyle}>
                  <option value="pcs">pcs</option>
                  <option value="sets">sets</option>
                  <option value="meters">meters</option>
                  <option value="rolls">rolls</option>
                  <option value="bags">bags</option>
                </select>
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 8 }}>
              <div>
                <label style={labelStyle}>Price (batch)</label>
                <input type="number" step="0.01" min="0" placeholder="£" value={form.price} onChange={e => setForm(f => ({ ...f, price: e.target.value }))} style={inputStyle} />
              </div>
              <div>
                <label style={labelStyle}>Low stock threshold</label>
                <input type="number" min="0" value={form.low_stock_threshold} onChange={e => setForm(f => ({ ...f, low_stock_threshold: e.target.value }))} style={inputStyle} />
              </div>
            </div>
            <div style={{ marginBottom: 8 }}>
              <label style={labelStyle}>Supplier</label>
              <input type="text" placeholder="e.g. Amazon, McMaster-Carr" value={form.supplier} onChange={e => setForm(f => ({ ...f, supplier: e.target.value }))} style={inputStyle} />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 8 }}>
              <div>
                <label style={labelStyle}>Purchase date</label>
                <input type="date" value={form.purchase_date} onChange={e => setForm(f => ({ ...f, purchase_date: e.target.value }))} style={inputStyle} />
              </div>
            </div>
            <div style={{ marginBottom: 12 }}>
              <label style={labelStyle}>Notes</label>
              <textarea value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} style={{ ...inputStyle, minHeight: 60 }} />
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button type="button" onClick={() => setShowAddModal(false)} style={smallBtnStyle}>Cancel</button>
              <button type="submit" style={btnStyle}>Add Bit</button>
            </div>
          </form>
        </Overlay>,
        document.body
      )}

      {/* Use Bit Modal */}
      {showUseModal && createPortal(
        <Overlay onClose={() => setShowUseModal(null)}>
          <h2 style={{ marginTop: 0, fontSize: '1.2rem' }}>Use: {showUseModal.name}</h2>
          <p style={{ opacity: 0.6, fontSize: '0.85rem' }}>Available: {showUseModal.quantity_remaining} {showUseModal.unit}</p>
          <form onSubmit={handleUseBit}>
            <div style={{ marginBottom: 8 }}>
              <label style={labelStyle}>Quantity used *</label>
              <input type="number" min="1" max={showUseModal.quantity_remaining} value={useForm.quantity_used} onChange={e => setUseForm(f => ({ ...f, quantity_used: e.target.value }))} style={inputStyle} required autoFocus />
            </div>
            <div style={{ marginBottom: 8 }}>
              <label style={labelStyle}>Project</label>
              <select value={useForm.project_id} onChange={e => setUseForm(f => ({ ...f, project_id: e.target.value }))} style={inputStyle}>
                <option value="">No project</option>
                {projects.filter(p => (p.status || 'active') === 'active').map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </div>
            <div style={{ marginBottom: 12 }}>
              <label style={labelStyle}>Notes</label>
              <input type="text" value={useForm.notes} onChange={e => setUseForm(f => ({ ...f, notes: e.target.value }))} style={inputStyle} />
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button type="button" onClick={() => setShowUseModal(null)} style={smallBtnStyle}>Cancel</button>
              <button type="submit" style={btnStyle}>Record Usage</button>
            </div>
          </form>
        </Overlay>,
        document.body
      )}

      {/* Restock Modal */}
      {showRestockModal && createPortal(
        <Overlay onClose={() => setShowRestockModal(null)}>
          <h2 style={{ marginTop: 0, fontSize: '1.2rem' }}>Restock: {showRestockModal.name}</h2>
          <p style={{ opacity: 0.6, fontSize: '0.85rem' }}>Current: {showRestockModal.quantity_remaining} / {showRestockModal.quantity_total} {showRestockModal.unit}</p>
          <form onSubmit={handleRestock}>
            <div style={{ marginBottom: 8 }}>
              <label style={labelStyle}>Quantity to add *</label>
              <input type="number" min="1" value={restockForm.quantity} onChange={e => setRestockForm(f => ({ ...f, quantity: e.target.value }))} style={inputStyle} required autoFocus />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 8 }}>
              <div>
                <label style={labelStyle}>New price</label>
                <input type="number" step="0.01" min="0" placeholder="£" value={restockForm.price} onChange={e => setRestockForm(f => ({ ...f, price: e.target.value }))} style={inputStyle} />
              </div>
              <div>
                <label style={labelStyle}>Purchase date</label>
                <input type="date" value={restockForm.purchase_date} onChange={e => setRestockForm(f => ({ ...f, purchase_date: e.target.value }))} style={inputStyle} />
              </div>
            </div>
            <div style={{ marginBottom: 12 }}>
              <label style={labelStyle}>Supplier</label>
              <input type="text" value={restockForm.supplier} onChange={e => setRestockForm(f => ({ ...f, supplier: e.target.value }))} style={inputStyle} />
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button type="button" onClick={() => setShowRestockModal(null)} style={smallBtnStyle}>Cancel</button>
              <button type="submit" style={btnStyle}>Restock</button>
            </div>
          </form>
        </Overlay>,
        document.body
      )}

      {/* Edit Bit Modal */}
      {editingBit && createPortal(
        <Overlay onClose={() => setEditingBit(null)}>
          <h2 style={{ marginTop: 0, fontSize: '1.2rem' }}>Edit Bit</h2>
          <form onSubmit={handleUpdateBit}>
            <div style={{ marginBottom: 8 }}>
              <label style={labelStyle}>Name</label>
              <input type="text" value={editingBit.name} onChange={e => setEditingBit(b => ({ ...b, name: e.target.value }))} style={inputStyle} required />
            </div>
            <div style={{ marginBottom: 8 }}>
              <label style={labelStyle}>Description</label>
              <input type="text" value={editingBit.description || ''} onChange={e => setEditingBit(b => ({ ...b, description: e.target.value }))} style={inputStyle} />
            </div>
            <div style={{ marginBottom: 8 }}>
              <label style={labelStyle}>Category</label>
              <select value={editingBit.category_id} onChange={e => setEditingBit(b => ({ ...b, category_id: e.target.value }))} style={inputStyle}>
                {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginBottom: 8 }}>
              <div>
                <label style={labelStyle}>Remaining</label>
                <input type="number" min="0" value={editingBit.quantity_remaining} onChange={e => setEditingBit(b => ({ ...b, quantity_remaining: e.target.value }))} style={inputStyle} />
              </div>
              <div>
                <label style={labelStyle}>Total</label>
                <input type="number" min="0" value={editingBit.quantity_total} onChange={e => setEditingBit(b => ({ ...b, quantity_total: e.target.value }))} style={inputStyle} />
              </div>
              <div>
                <label style={labelStyle}>Low stock</label>
                <input type="number" min="0" value={editingBit.low_stock_threshold} onChange={e => setEditingBit(b => ({ ...b, low_stock_threshold: e.target.value }))} style={inputStyle} />
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 8 }}>
              <div>
                <label style={labelStyle}>Unit</label>
                <select value={editingBit.unit} onChange={e => setEditingBit(b => ({ ...b, unit: e.target.value }))} style={inputStyle}>
                  <option value="pcs">pcs</option>
                  <option value="sets">sets</option>
                  <option value="meters">meters</option>
                  <option value="rolls">rolls</option>
                  <option value="bags">bags</option>
                </select>
              </div>
              <div>
                <label style={labelStyle}>Price</label>
                <input type="number" step="0.01" min="0" value={editingBit.price || ''} onChange={e => setEditingBit(b => ({ ...b, price: e.target.value }))} style={inputStyle} />
              </div>
            </div>
            <div style={{ marginBottom: 8 }}>
              <label style={labelStyle}>Supplier</label>
              <input type="text" value={editingBit.supplier || ''} onChange={e => setEditingBit(b => ({ ...b, supplier: e.target.value }))} style={inputStyle} />
            </div>
            <div style={{ marginBottom: 12 }}>
              <label style={labelStyle}>Notes</label>
              <textarea value={editingBit.notes || ''} onChange={e => setEditingBit(b => ({ ...b, notes: e.target.value }))} style={{ ...inputStyle, minHeight: 60 }} />
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button type="button" onClick={() => setEditingBit(null)} style={smallBtnStyle}>Cancel</button>
              <button type="submit" style={btnStyle}>Save</button>
            </div>
          </form>
        </Overlay>,
        document.body
      )}
    </div>
  );
}


// --- Shared UI components ---

function StatCard({ label, value, accent }) {
  return (
    <div style={{
      padding: '0.75rem 1rem',
      borderRadius: 8,
      background: 'var(--color-surface-alt, #2a2a2a)',
      border: '1px solid var(--color-border, #444)',
    }}>
      <div style={{ fontSize: '0.75rem', opacity: 0.6, marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: '1.25rem', fontWeight: 700, color: accent ? 'var(--color-warning, #e8a735)' : 'inherit' }}>{value}</div>
    </div>
  );
}

function Overlay({ onClose, children }) {
  return (
    <div
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex',
        alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: '1rem',
      }}
    >
      <div style={{
        background: 'var(--color-surface, #1e1e1e)', borderRadius: 12,
        padding: '1.5rem', maxWidth: 480, width: '100%', maxHeight: '90vh', overflow: 'auto',
        border: '1px solid var(--color-border, #444)',
      }}>
        {children}
      </div>
    </div>
  );
}

// --- Styles ---

const btnStyle = {
  padding: '0.5rem 1.25rem',
  borderRadius: 6,
  border: 'none',
  background: 'var(--color-accent, #5ba85b)',
  color: '#fff',
  fontWeight: 600,
  cursor: 'pointer',
  fontSize: '0.9rem',
};

const smallBtnStyle = {
  padding: '0.3rem 0.7rem',
  borderRadius: 4,
  border: '1px solid var(--color-border, #444)',
  background: 'transparent',
  color: 'inherit',
  cursor: 'pointer',
  fontSize: '0.8rem',
};

const tabBtnStyle = {
  padding: '0.25rem 0.6rem',
  borderRadius: 4,
  border: '1px solid var(--color-border, #444)',
  background: 'transparent',
  color: 'inherit',
  cursor: 'pointer',
  fontSize: '0.8rem',
};

const inputStyle = {
  width: '100%',
  padding: '0.45rem 0.6rem',
  borderRadius: 4,
  border: '1px solid var(--color-border, #444)',
  background: 'var(--color-surface-alt, #2a2a2a)',
  color: 'inherit',
  fontSize: '0.9rem',
  boxSizing: 'border-box',
};

const labelStyle = {
  display: 'block',
  fontSize: '0.8rem',
  opacity: 0.7,
  marginBottom: 2,
};

const cardStyle = {
  padding: '0.75rem 1rem',
  borderRadius: 8,
  background: 'var(--color-surface-alt, #2a2a2a)',
  border: '1px solid var(--color-border, #444)',
};
