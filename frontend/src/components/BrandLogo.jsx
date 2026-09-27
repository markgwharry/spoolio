import React from 'react';

export default function BrandLogo({ showWordmark = true, className = '' }) {
  return (
    <span className={`brand-logo ${className}`.trim()}>
      <img
        className="brand-logo-mark"
        src="/spoolio-mark.png"
        alt="Spoolio logo"
      />
      {showWordmark && <span className="brand-logo-wordmark">Spoolio</span>}
    </span>
  );
}
