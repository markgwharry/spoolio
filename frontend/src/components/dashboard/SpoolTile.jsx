import React from 'react';
import { parseColorName, isLightColor, getLuminance, formatGrams } from '../../utils/colorUtils';

export default function SpoolTile({ color, count, totalWeight, onClick, faded, highlight, reserveCount = 0, reserveWeight = 0 }) {
  const fillColors = parseColorName(color);
  let fillId = '';
  let fill = fillColors[0];
  let gradientDef = null;
  // Determine text color based on both color luminance AND theme mode
  const primaryColor = fillColors[0] === 'rainbow' ? '#9b59b6' : fillColors[0];
  const colorIsLight = isLightColor(primaryColor);
  const isDarkMode = !document.documentElement.classList.contains('light');
  // In light mode: light colors need dark text, dark colors use the color
  // In dark mode: dark colors need light text, light colors use the color
  const textColor = isDarkMode
    ? (colorIsLight ? primaryColor : '#eee')
    : (colorIsLight ? '#222' : primaryColor);
  if (fillColors.length > 1) {
    fillId = `gradient-${color.replace(/\s+/g, '-')}`;
    gradientDef = (
      <linearGradient id={fillId} x1="0%" y1="0%" x2="100%" y2="0%">
        {fillColors.map((c, i) => (
          <stop key={i} offset={`${(i/(fillColors.length-1))*100}%`} stopColor={c} />
        ))}
      </linearGradient>
    );
    fill = `url(#${fillId})`;
  } else if (fillColors[0] === 'rainbow') {
    fillId = 'rainbow-gradient';
    gradientDef = (
      <linearGradient id="rainbow-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
        <stop offset="0%" stopColor="#e74c3c" />
        <stop offset="16%" stopColor="#f1c40f" />
        <stop offset="33%" stopColor="#27ae60" />
        <stop offset="50%" stopColor="#3498db" />
        <stop offset="66%" stopColor="#9b59b6" />
        <stop offset="83%" stopColor="#ff69b4" />
        <stop offset="100%" stopColor="#e74c3c" />
      </linearGradient>
    );
    fill = 'url(#rainbow-gradient)';
  }

  // Determine accent color based on the first parsed fill color
  const accentColor = fillColors[0] === 'rainbow' ? '#9b59b6' : fillColors[0];

  // --- Dark/light/clear filament handling (a pain no competitor solves) ---
  // Very dark filament vanishes on the dark flange/page; very light vanishes in
  // light mode; clear/transparent has no colour at all. We give the coil an
  // adaptive contrast ring, flip the winding-line colour, and back transparent
  // filament with a checkerboard so it always reads.
  const isMulti = fillColors.length > 1 || fillColors[0] === 'rainbow';
  const lum = isMulti ? 0.5 : getLuminance(primaryColor);
  const isVeryDark = !isMulti && lum < 0.12;
  const isVeryLight = !isMulti && lum > 0.85;
  const isClear = /\b(clear|transparent|translucent)\b/i.test(color || '');
  const coilRing = isVeryDark ? 'rgba(255,255,255,0.7)'
    : isVeryLight ? 'rgba(0,0,0,0.45)'
    : 'rgba(0,0,0,0.22)';
  const coilRingWidth = (isVeryDark || isVeryLight) ? 2 : 1.25;
  const windingStroke = isVeryDark ? 'rgba(255,255,255,0.18)' : 'rgba(0,0,0,0.16)';

  // Face-on spool gauge: the wound-filament ring thins as the spool depletes.
  // Capacity is approximated as ~1kg per spool, so the coil shows average
  // fullness across the spools in this colour group.
  const capacity = Math.max(1, count) * 1000;
  const fullness = Math.max(0.04, Math.min(1, (totalWeight || 0) / capacity));
  const HUB = 9;
  const MAX_COIL = 25;
  const coilR = HUB + (MAX_COIL - HUB) * fullness;
  // A few concentric winding lines within the coil for a tactile, wound look.
  const windings = [];
  for (let r = HUB + 3; r < coilR - 1; r += 3.2) {
    windings.push(<circle key={r} cx="32" cy="32" r={r} fill="none" stroke={windingStroke} strokeWidth="0.8" />);
  }

  return (
    <button
      type="button"
      className={`spool-card${highlight ? ' low-stock' : ''}${faded ? ' faded' : ''}`}
      onClick={onClick}
      title={`${color} – ${count} active spools${reserveCount ? `, ${reserveCount} in reserve` : ''}`}
      aria-label={`${color}: ${count} active spools${reserveCount ? `, ${reserveCount} reserve` : ''}`}
      style={{ '--spool-accent': accentColor, '--spool-text': textColor }}
    >
      <div className="spool-visual">
        <svg width="64" height="64" viewBox="0 0 64 64" role="img" aria-hidden="true">
          <defs>
            {gradientDef}
            <pattern id="spool-checker" width="6" height="6" patternUnits="userSpaceOnUse">
              <rect width="6" height="6" fill="#ffffff" />
              <rect width="3" height="3" fill="#c9c9c9" />
              <rect x="3" y="3" width="3" height="3" fill="#c9c9c9" />
            </pattern>
          </defs>
          {/* flange */}
          <circle cx="32" cy="32" r="28" fill="var(--surface-3)" stroke="var(--border)" strokeWidth="1.5" />
          <circle cx="32" cy="32" r="26" fill="none" stroke="rgba(0,0,0,0.25)" strokeWidth="1" />
          {/* transparent/clear filament gets a checkerboard so it reads */}
          {isClear && <circle className="spool-coil" cx="32" cy="32" r={coilR} fill="url(#spool-checker)" />}
          {/* wound filament — radius scales with remaining weight; adaptive ring
              keeps very dark / very light filament visible against any backdrop.
              .spool-coil animates the radius so it depletes when usage is logged. */}
          <circle className="spool-coil" cx="32" cy="32" r={coilR} fill={fill} fillOpacity={isClear ? 0.5 : 1}
            stroke={coilRing} strokeWidth={coilRingWidth} />
          {windings}
          {/* hub + centre hole */}
          <circle cx="32" cy="32" r={HUB} fill="var(--surface-2)" stroke="var(--border)" strokeWidth="1.5" />
          <circle cx="32" cy="32" r="2.5" fill="var(--background)" />
        </svg>
      </div>
      <div className="spool-info">
        <div className="spool-color-name">{color}</div>
        <div className="spool-count" style={{ fontFamily: 'var(--font-mono)' }}>
          {count}
          {reserveCount > 0 && <span className="reserve-badge">+{reserveCount}</span>}
        </div>
        <div className="spool-label">{count === 1 ? 'spool' : 'spools'}</div>
        <div className="spool-weight" style={{ fontFamily: 'var(--font-mono)' }}>
          {formatGrams(totalWeight)}g
          {reserveWeight > 0 && <span className="reserve-weight"> (+{formatGrams(reserveWeight)}g)</span>}
        </div>
      </div>
      <div className="stock-bar">
        <div
          className="stock-bar-fill"
          style={{ width: `${Math.round(fullness * 100)}%` }}
        />
      </div>
      {reserveCount > 0 && <span className="tag reserve-tag">Reserve</span>}
    </button>
  );
}
