import React from 'react';

/**
 * Branded loading indicator: a spool whose amber filament arc rotates, as if
 * feeding. Reuses the signature spool-gauge motif so loading feels on-brand
 * instead of a generic spinner.
 */
export default function SpoolSpinner({ label = 'Loading…', size = 52 }) {
  return (
    <div className="spool-spinner" role="status" aria-live="polite">
      <svg
        className="spool-spinner-svg"
        width={size}
        height={size}
        viewBox="0 0 64 64"
        aria-hidden="true"
      >
        {/* flange + empty coil bed */}
        <circle cx="32" cy="32" r="28" fill="none" stroke="var(--border)" strokeWidth="2.5" />
        <circle cx="32" cy="32" r="20" fill="none" stroke="var(--surface-3)" strokeWidth="7" />
        {/* rotating amber filament arc */}
        <circle
          cx="32" cy="32" r="20" fill="none"
          stroke="var(--accent)" strokeWidth="7" strokeLinecap="round"
          strokeDasharray="46 126"
        />
        {/* hub */}
        <circle cx="32" cy="32" r="8" fill="var(--surface-2)" stroke="var(--border)" strokeWidth="2" />
        <circle cx="32" cy="32" r="2.5" fill="var(--background)" />
      </svg>
      {label && <span className="spool-spinner-label">{label}</span>}
    </div>
  );
}
