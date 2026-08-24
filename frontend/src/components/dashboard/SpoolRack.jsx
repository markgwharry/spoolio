import React from 'react';
import {
  colorSortKey,
  formatGrams,
  parseColorName,
} from '../../utils/colorUtils';

export default function SpoolRack({ items, onSpoolClick }) {
  const ordered = [...(items || [])].sort((a, b) => {
    const aName = (a && (a.colorName || a.color)) || '';
    const bName = (b && (b.colorName || b.color)) || '';
    return colorSortKey(aName) - colorSortKey(bName);
  });

  return (
    <div className="spool-rack" aria-label="Spool rack overview" role="list">
      {ordered.slice(0, 150).map((item, index) => {
        const parsedColors = parseColorName(item.colorName || item.color || '');
        const background = Array.isArray(parsedColors) ? parsedColors[0] : parsedColors;
        const percent = Math.max(5, Math.min(
          100,
          Math.round(((item.weight_remaining ?? item.weight_total ?? 0) / 1000) * 100),
        ));
        const isLow = !item.is_empty
          && (item.weight_remaining ?? 0) <= (item.low_stock_threshold ?? 100);
        const weight = formatGrams(item.weight_remaining ?? item.weight_total);
        const label = `${item.materialName || ''} ${item.colorName || ''}`;

        return (
          <div
            key={`${item.id || index}`}
            className={`spool-rack-square${isLow ? ' low' : ''}`}
            style={{ background }}
            tabIndex={0}
            role="listitem"
            aria-label={`${label}, ${weight} grams remaining`}
            title={`${label} – ${weight}g – Click to view`}
            onClick={() => onSpoolClick?.(item)}
            onKeyDown={(event) => event.key === 'Enter' && onSpoolClick?.(item)}
          >
            <div className="spool-rack-fillbar" style={{ width: `${percent}%` }} />
            <span className="spool-tooltip">
              {(item.materialName || item.material || '')} – {(item.colorName || item.color || '')}
              <br />
              Weight: {weight}g
            </span>
          </div>
        );
      })}
    </div>
  );
}
