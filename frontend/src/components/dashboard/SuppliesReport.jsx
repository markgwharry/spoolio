import React, { useMemo } from 'react';
import { formatGrams } from '../../utils/colorUtils';

const headerCellStyle = {
  padding: '8px 6px',
  borderBottom: '1px solid var(--border)',
  color: 'var(--muted-foreground)',
};

const cellStyle = {
  padding: '6px 6px',
  borderBottom: '1px solid var(--border)',
};

export function buildSuppliesReportRows({
  spools,
  refills,
  materials,
  colors,
  filters,
}) {
  const materialMap = Object.fromEntries(materials.map((material) => [material.id, material.name]));
  const colorMap = Object.fromEntries(colors.map((color) => [color.id, color.name]));
  const keyFor = (materialId, subtype, colorId) => (
    `${materialId}|${(subtype || '').trim().toLowerCase() || 'basic'}|${colorId}`
  );
  const displaySubtype = (subtype) => (subtype && subtype.trim() ? subtype.trim() : 'Basic');
  const aggregate = {};

  (Array.isArray(spools) ? spools : []).forEach((spool) => {
    if (spool.is_empty) return;
    if (filters.materialId && String(spool.material_id) !== String(filters.materialId)) return;
    if (filters.colorId && String(spool.color_id) !== String(filters.colorId)) return;
    if (filters.manufacturerId && String(spool.manufacturer_id) !== String(filters.manufacturerId)) return;
    if (filters.subtypeMode === 'basic' && spool.subtype?.trim()) return;
    if (filters.subtypeMode === 'nonbasic' && !spool.subtype?.trim()) return;
    if (filters.lowStockOnly
      && !(spool.weight_remaining <= (spool.low_stock_threshold ?? 100))) return;

    const key = keyFor(spool.material_id, spool.subtype, spool.color_id);
    if (!aggregate[key]) {
      aggregate[key] = {
        material_id: spool.material_id,
        color_id: spool.color_id,
        subtype: displaySubtype(spool.subtype),
        activeWeight: 0,
        activeCount: 0,
        reserveWeight: 0,
        reserveCount: 0,
      };
    }
    aggregate[key].activeWeight += spool.weight_remaining || 0;
    aggregate[key].activeCount += 1;
  });

  (filters.includeRefills ? (Array.isArray(refills) ? refills : []) : []).forEach((refill) => {
    if (filters.materialId && String(refill.material_id) !== String(filters.materialId)) return;
    if (filters.colorId && String(refill.color_id) !== String(filters.colorId)) return;
    if (filters.manufacturerId && String(refill.manufacturer_id) !== String(filters.manufacturerId)) return;
    if (filters.subtypeMode === 'basic' && String(refill.subtype || '').trim()) return;
    if (filters.subtypeMode === 'nonbasic' && !String(refill.subtype || '').trim()) return;

    const key = keyFor(refill.material_id, refill.subtype, refill.color_id);
    if (!aggregate[key]) {
      aggregate[key] = {
        material_id: refill.material_id,
        color_id: refill.color_id,
        subtype: displaySubtype(refill.subtype),
        activeWeight: 0,
        activeCount: 0,
        reserveWeight: 0,
        reserveCount: 0,
      };
    }
    aggregate[key].reserveWeight += typeof refill.weight_remaining === 'number'
      ? refill.weight_remaining
      : (refill.weight_total || 0);
    aggregate[key].reserveCount += 1;
  });

  return Object.values(aggregate).map((row) => ({
    ...row,
    material: materialMap[row.material_id] || 'Unknown',
    color: colorMap[row.color_id] || 'Unknown',
    totalWeight: (row.activeWeight || 0) + (row.reserveWeight || 0),
  })).sort((a, b) => (a.activeWeight || 0) - (b.activeWeight || 0));
}

export default function SuppliesReport({
  open,
  spools,
  refills,
  materials,
  colors,
  filters,
  onClose,
}) {
  const rows = useMemo(() => buildSuppliesReportRows({
    spools,
    refills,
    materials,
    colors,
    filters,
  }), [spools, refills, materials, colors, filters]);

  if (!open) return null;

  return (
    <div style={{ position: 'fixed', inset: 0, background: '#0008', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{
        background: 'var(--card)',
        color: 'var(--card-foreground)',
        border: '1px solid var(--border)',
        borderRadius: 12,
        padding: 16,
        width: '90%',
        maxWidth: 900,
        maxHeight: '80%',
        overflow: 'auto',
        boxShadow: '0 12px 40px rgba(7, 16, 32, 0.22)',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <h3 style={{ margin: 0 }}>Supplies Report</h3>
          <button onClick={onClose}>Close</button>
        </div>
        <div style={{ fontSize: 12, color: 'var(--muted-foreground)', marginBottom: 8 }}>
          Grouped by Material → Subtype → Color. Sorted by active weight remaining ascending.
        </div>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ background: 'var(--muted)' }}>
              <th style={{ ...headerCellStyle, textAlign: 'left' }}>Material</th>
              <th style={{ ...headerCellStyle, textAlign: 'left' }}>Subtype</th>
              <th style={{ ...headerCellStyle, textAlign: 'left' }}>Color</th>
              <th style={{ ...headerCellStyle, textAlign: 'right' }}>Active spools</th>
              <th style={{ ...headerCellStyle, textAlign: 'right' }}>Active weight (g)</th>
              <th style={{ ...headerCellStyle, textAlign: 'right' }}>Refills (count)</th>
              <th style={{ ...headerCellStyle, textAlign: 'right' }}>Refill weight (g)</th>
              <th style={{ ...headerCellStyle, textAlign: 'right' }}>Total (g)</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.material_id}-${row.subtype}-${row.color_id}`}>
                <td style={cellStyle}>{row.material}</td>
                <td style={cellStyle}>{row.subtype}</td>
                <td style={cellStyle}>{row.color}</td>
                <td style={{ ...cellStyle, textAlign: 'right' }}>{row.activeCount}</td>
                <td style={{ ...cellStyle, textAlign: 'right' }}>{formatGrams(row.activeWeight)}</td>
                <td style={{ ...cellStyle, textAlign: 'right' }}>{row.reserveCount}</td>
                <td style={{ ...cellStyle, textAlign: 'right' }}>{formatGrams(row.reserveWeight)}</td>
                <td style={{ ...cellStyle, textAlign: 'right' }}>{formatGrams(row.totalWeight)}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={8} style={{ padding: 12, textAlign: 'center', color: 'var(--muted-foreground)' }}>
                  No supplies to report.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
