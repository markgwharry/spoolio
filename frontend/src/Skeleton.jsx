import React from 'react';

export function Skeleton({ width, height, variant = 'text', className = '' }) {
  const style = {
    width: width || '100%',
    height: height || (variant === 'text' ? '1em' : variant === 'circular' ? width : '100%'),
    borderRadius: variant === 'circular' ? '50%' : variant === 'rectangular' ? '4px' : '4px'
  };

  return (
    <div
      className={`skeleton skeleton-${variant} ${className}`}
      style={style}
      aria-hidden="true"
    />
  );
}

export function SkeletonCard({ showImage = true }) {
  return (
    <div className="skeleton-card" aria-hidden="true">
      {showImage && <Skeleton variant="rectangular" height="120px" />}
      <div className="skeleton-card-content">
        <Skeleton variant="text" width="60%" height="1.25em" />
        <Skeleton variant="text" width="80%" />
        <Skeleton variant="text" width="40%" />
      </div>
    </div>
  );
}

export function SkeletonSpoolGrid({ count = 8 }) {
  return (
    <div className="skeleton-spool-grid" aria-label="Loading spools...">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="skeleton-spool-card">
          <Skeleton variant="rectangular" height="56px" width="56px" />
          <div className="skeleton-spool-info">
            <Skeleton variant="text" width="80%" />
            <Skeleton variant="text" width="40%" />
            <Skeleton variant="text" width="60%" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function SkeletonStatsGrid() {
  return (
    <div className="skeleton-stats-grid" aria-label="Loading stats...">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="skeleton-stat-card">
          <Skeleton variant="circular" width="40px" height="40px" />
          <Skeleton variant="text" width="60px" height="2em" />
          <Skeleton variant="text" width="80px" />
        </div>
      ))}
    </div>
  );
}

export function SkeletonTable({ rows = 5, columns = 4 }) {
  return (
    <div className="skeleton-table" aria-label="Loading table...">
      <div className="skeleton-table-header">
        {Array.from({ length: columns }).map((_, i) => (
          <Skeleton key={i} variant="text" width="100px" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, rowIdx) => (
        <div key={rowIdx} className="skeleton-table-row">
          {Array.from({ length: columns }).map((_, colIdx) => (
            <Skeleton key={colIdx} variant="text" width={colIdx === 0 ? '150px' : '80px'} />
          ))}
        </div>
      ))}
    </div>
  );
}

export default Skeleton;
