import React from 'react';

/**
 * An inviting empty state built around a "ghost" spool-gauge outline — a fresh
 * canvas rather than a dead grid. Optionally renders a primary action.
 */
export default function EmptyState({ title, message, actionLabel, onAction }) {
  return (
    <div className="empty-state empty-state--branded">
      <svg
        className="empty-state-gauge"
        width="72" height="72" viewBox="0 0 64 64" aria-hidden="true"
      >
        {/* dashed ghost spool: flange, coil bed and hub, all as outlines */}
        <circle cx="32" cy="32" r="28" fill="none" stroke="var(--border)" strokeWidth="2"
          strokeDasharray="4 4" />
        <circle cx="32" cy="32" r="20" fill="none" stroke="var(--accent)" strokeWidth="2"
          strokeDasharray="4 5" opacity="0.7" />
        <circle cx="32" cy="32" r="8" fill="none" stroke="var(--border)" strokeWidth="2" />
      </svg>
      {title && <p className="empty-state-title">{title}</p>}
      {message && <p className="empty-state-message">{message}</p>}
      {actionLabel && onAction && (
        <button type="button" className="button" onClick={onAction}>
          {actionLabel}
        </button>
      )}
    </div>
  );
}
