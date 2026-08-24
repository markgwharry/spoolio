import React from 'react';

export default function StatsGrid({ spools, emptySpools }) {
  const activeSpools = spools.filter(s => !s.is_empty);
  const totalWeight = activeSpools.reduce((sum, s) => sum + (s.weight_remaining || 0), 0);
  const lowStockCount = activeSpools.filter(s => s.weight_remaining <= (s.low_stock_threshold ?? 100)).length;
  const emptyCount = (emptySpools || []).length;

  const stats = [
    { label: 'Total Spools', value: activeSpools.length, icon: 'spool' },
    { label: 'Total Weight', value: `${(totalWeight / 1000).toFixed(1)}kg`, icon: 'weight' },
    { label: 'Low Stock', value: lowStockCount, icon: 'warning', accent: lowStockCount > 0 ? 'destructive' : null },
    { label: 'Empty Spools', value: emptyCount, icon: 'empty' }
  ];

  return (
    <div className="stats-grid">
      {stats.map((stat, idx) => (
        <div
          key={stat.label}
          className={`stat-card${stat.accent ? ` accent-${stat.accent}` : ''}`}
          style={{ animationDelay: `${idx * 50}ms` }}
        >
          <div className="stat-icon">
            {stat.icon === 'spool' && (
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3"/>
              </svg>
            )}
            {stat.icon === 'weight' && (
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 2v20M2 12h20"/><circle cx="12" cy="12" r="4"/>
              </svg>
            )}
            {stat.icon === 'warning' && (
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
              </svg>
            )}
            {stat.icon === 'empty' && (
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10"/><path d="M8 12h8"/>
              </svg>
            )}
          </div>
          <div className="stat-value">{stat.value}</div>
          <div className="stat-label">{stat.label}</div>
        </div>
      ))}
    </div>
  );
}
