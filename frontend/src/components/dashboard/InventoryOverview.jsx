import React, { useMemo, useState } from 'react';
import { formatGrams } from '../../utils/colorUtils';
import EmptyState from '../EmptyState';

export default function InventoryOverview({
  spools,
  refills,
  materials,
  colors,
  manufacturers,
  spoolTypes,
  onAddSpool,
  onJumpToSpool,
}) {
  const [showLowStockPopup, setShowLowStockPopup] = useState(true);
  const activeSpools = useMemo(
    () => spools.filter((spool) => !spool.is_empty),
    [spools],
  );
  const lowStockSpools = activeSpools.filter(
    (spool) => spool.weight_remaining <= (spool.low_stock_threshold ?? 100),
  );
  const names = {
    material: Object.fromEntries(materials.map((item) => [item.id, item.name])),
    color: Object.fromEntries(colors.map((item) => [item.id, item.name])),
    manufacturer: Object.fromEntries(manufacturers.map((item) => [item.id, item.name])),
    spoolType: Object.fromEntries(spoolTypes.map((item) => [item.id, item.name])),
  };

  const otherStock = (spool) => {
    const otherSpools = spools.filter((candidate) => (
      candidate.material_id === spool.material_id
      && candidate.color_id === spool.color_id
      && candidate.id !== spool.id
      && !candidate.is_empty
    ));
    const matchingRefills = refills.filter((refill) => (
      refill.material_id === spool.material_id && refill.color_id === spool.color_id
    ));
    return {
      otherSpoolCount: otherSpools.length,
      refillCount: matchingRefills.length,
      totalWeight: otherSpools.reduce(
        (sum, item) => sum + (item.weight_remaining || 0),
        0,
      ) + matchingRefills.reduce(
        (sum, item) => sum + (item.weight_remaining ?? item.weight_total ?? 0),
        0,
      ),
    };
  };

  return (
    <>
      {showLowStockPopup && lowStockSpools.length > 0 && (
        <div className={`banner warning${showLowStockPopup === 'closing' ? ' closing' : ''}`}>
          <div className="banner-content">
            <svg className="banner-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
              <line x1="12" y1="9" x2="12" y2="13" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
            <div>
              <strong>Low stock alert</strong>
              <ul className="banner-list">
                {lowStockSpools.map((spool) => {
                  const stock = otherStock(spool);
                  const stockParts = [];
                  if (stock.otherSpoolCount > 0) {
                    stockParts.push(`${stock.otherSpoolCount} spool${stock.otherSpoolCount > 1 ? 's' : ''}`);
                  }
                  if (stock.refillCount > 0) {
                    stockParts.push(`${stock.refillCount} refill${stock.refillCount > 1 ? 's' : ''}`);
                  }
                  const material = names.material[spool.material_id] || '';
                  const color = names.color[spool.color_id] || '';
                  const manufacturer = names.manufacturer[spool.manufacturer_id] || '';
                  const spoolType = names.spoolType[spool.spool_type_id] || '';
                  return (
                    <li key={spool.id} onClick={() => onJumpToSpool(spool)}>
                      <div>
                        {material} {color} {manufacturer && `— ${manufacturer}`} {spoolType && `(${spoolType})`} — {formatGrams(spool.weight_remaining)}g left
                      </div>
                      {stock.totalWeight > 0 && (
                        <div className="low-stock-total">
                          Total {color} {material} available: {formatGrams(spool.weight_remaining + stock.totalWeight)}g (across {stockParts.join(' + ')})
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          </div>
          <button
            onClick={() => {
              setShowLowStockPopup('closing');
              setTimeout(() => setShowLowStockPopup(false), 180);
            }}
            className="banner-dismiss"
            aria-label="Dismiss"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      )}

      <section className="library-hero">
        <div className="library-hero-copy">
          <p className="eyebrow">Your workshop</p>
          <h1>Filament library</h1>
          <p>See what is ready to print, what is running low, and what is waiting in reserve.</p>
        </div>
        <div className="library-hero-actions">
          <button type="button" className="button add-spool-btn" onClick={onAddSpool}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M12 5v14M5 12h14" />
            </svg>
            Add Spool
          </button>
        </div>
      </section>
      {activeSpools.length === 0 && (
        <div className="first-run-card">
          <EmptyState
            title="Build your first filament rack"
            message="Add one spool and Spoolio will start tracking its colour, remaining weight and estimated cost."
            actionLabel="Add your first spool"
            onAction={onAddSpool}
          />
          <ol className="first-run-steps" aria-label="Getting started">
            <li><span>1</span>Choose the filament</li>
            <li><span>2</span>Enter its weight</li>
            <li><span>3</span>Print with confidence</li>
          </ol>
        </div>
      )}
    </>
  );
}
