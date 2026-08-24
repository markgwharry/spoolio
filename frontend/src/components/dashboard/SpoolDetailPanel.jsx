import React, { useContext, useEffect, useState, useMemo } from 'react';
import { AuthContext } from '../../AuthContext';
import { formatGrams } from '../../utils/colorUtils';

export default function SpoolDetailPanel({ spool, history, onClose, onRecordUsage, onHistoryUpdate }) {
  const { authFetch } = useContext(AuthContext);
  const [projects, setProjects] = useState([]);
  const [assigningEntryId, setAssigningEntryId] = useState(null);
  const [selectMode, setSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [bulkProjectId, setBulkProjectId] = useState('');
  const [bulkAssigning, setBulkAssigning] = useState(false);

  // Fetch projects once on mount
  useEffect(() => {
    let cancelled = false;
    authFetch('/api/projects/').then(res => res.ok ? res.json() : null).then(data => {
      if (!cancelled && data) setProjects(data.projects || []);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [authFetch]);

  const handleAssignProject = async (entryId, projectId) => {
    try {
      const res = await authFetch(`/api/spoolhistory/${entryId}/`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId || null })
      });
      if (res.ok) {
        const data = await res.json();
        if (onHistoryUpdate) onHistoryUpdate(data.history);
      }
    } catch (e) {
      // Failed to assign project
    }
    setAssigningEntryId(null);
  };

  const handleBulkAssign = async () => {
    setBulkAssigning(true);
    try {
      const res = await authFetch('/api/spoolhistory/bulk-assign', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          history_ids: Array.from(selectedIds),
          project_id: bulkProjectId ? parseInt(bulkProjectId) : null
        })
      });
      if (res.ok) {
        const data = await res.json();
        if (onHistoryUpdate && data.history) {
          onHistoryUpdate(data.history);
        }
        setSelectedIds(new Set());
        setSelectMode(false);
        setBulkProjectId('');
      }
    } catch (e) {
      // Bulk assign failed
    }
    setBulkAssigning(false);
  };

  // Calculate weight over time from history
  // Start from current weight and work backwards to reconstruct timeline
  const sortedHistory = useMemo(() => {
    if (!history || history.length === 0) return [];
    return [...history]
      .filter(h => h.spool_id === spool.id)
      .sort((a, b) => new Date(a.date) - new Date(b.date));
  }, [history, spool.id]);

  // Build data points for the graph
  const graphData = useMemo(() => {
    if (sortedHistory.length === 0) {
      // No history - just show current weight as a single point
      return [{ date: new Date(), weight: spool.weight_remaining }];
    }

    // Calculate starting weight by adding back all usage
    const totalUsed = sortedHistory.reduce((sum, h) => sum + (h.weight_used || 0), 0);
    const startingWeight = (spool.weight_remaining || 0) + totalUsed;

    // Build cumulative timeline
    const points = [{ date: new Date(sortedHistory[0].date), weight: startingWeight }];
    let currentWeight = startingWeight;

    sortedHistory.forEach(entry => {
      currentWeight -= (entry.weight_used || 0);
      points.push({ date: new Date(entry.date), weight: Math.max(0, currentWeight) });
    });

    // Add current state if last entry isn't recent (within 1 day)
    const lastPoint = points[points.length - 1];
    const now = new Date();
    if (now - lastPoint.date > 24 * 60 * 60 * 1000) {
      points.push({ date: now, weight: spool.weight_remaining });
    }

    return points;
  }, [sortedHistory, spool.weight_remaining]);

  // SVG graph dimensions (static)
  const graphWidth = 320;
  const graphHeight = 140;
  const graphPadding = { top: 20, right: 20, bottom: 30, left: 45 };
  const innerWidth = graphWidth - graphPadding.left - graphPadding.right;
  const innerHeight = graphHeight - graphPadding.top - graphPadding.bottom;

  // Calculate scales
  const { maxWeight, minDate, maxDate, pathD, points } = useMemo(() => {
    if (graphData.length === 0) return { maxWeight: 1000, minDate: new Date(), maxDate: new Date(), pathD: '', points: [] };

    const weights = graphData.map(d => d.weight);
    const dates = graphData.map(d => d.date.getTime());

    const minW = 0;
    const maxW = Math.max(...weights) * 1.1; // 10% padding
    const minD = Math.min(...dates);
    const maxD = Math.max(...dates);
    const dateRange = maxD - minD || 1;

    // Generate path and points
    const pts = graphData.map(d => ({
      x: graphPadding.left + ((d.date.getTime() - minD) / dateRange) * innerWidth,
      y: graphPadding.top + innerHeight - ((d.weight - minW) / (maxW - minW)) * innerHeight,
      weight: d.weight,
      date: d.date
    }));

    // Create SVG path
    const path = pts.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');

    return { maxWeight: maxW, minDate: new Date(minD), maxDate: new Date(maxD), pathD: path, points: pts };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphData, innerWidth, innerHeight]); // graphPadding is a static constant

  // Format date for display
  const formatDate = (date) => {
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  // Y-axis labels
  const yLabels = [0, Math.round(maxWeight / 2), Math.round(maxWeight)];

  return (
    <div className="spool-detail-panel">
      <div className="spool-detail-panel-header">
        <div className="spool-detail-panel-title">
          <span className="spool-detail-panel-manufacturer">{spool.manufacturer}</span>
          <span className="spool-detail-panel-material">{spool.materialName} {spool.colorName}</span>
          {spool.subtype && <span className="spool-detail-panel-subtype">{spool.subtype}</span>}
        </div>
        <button type="button" className="spool-detail-panel-close" onClick={onClose} aria-label="Close">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 6L6 18M6 6l12 12"/>
          </svg>
        </button>
      </div>

      <div className="spool-detail-panel-current">
        <div className="spool-detail-panel-weight">{formatGrams(spool.weight_remaining)}g</div>
        <div className="spool-detail-panel-weight-label">remaining</div>
      </div>

      <div className="spool-detail-panel-graph">
        <div className="spool-detail-panel-graph-title">Remaining Filament Over Time</div>
        <svg width={graphWidth} height={graphHeight} className="usage-graph">
          {/* Grid lines */}
          {yLabels.map((label, i) => {
            const y = graphPadding.top + innerHeight - (label / maxWeight) * innerHeight;
            return (
              <g key={i}>
                <line
                  x1={graphPadding.left}
                  y1={y}
                  x2={graphPadding.left + innerWidth}
                  y2={y}
                  stroke="var(--border-subtle)"
                  strokeDasharray="2,2"
                />
                <text
                  x={graphPadding.left - 8}
                  y={y + 4}
                  textAnchor="end"
                  className="graph-label"
                >
                  {label}g
                </text>
              </g>
            );
          })}

          {/* Area fill */}
          {pathD && (
            <path
              d={`${pathD} L ${points[points.length - 1]?.x || graphPadding.left} ${graphPadding.top + innerHeight} L ${graphPadding.left} ${graphPadding.top + innerHeight} Z`}
              fill="var(--accent)"
              fillOpacity="0.1"
              className="graph-area"
            />
          )}

          {/* Line */}
          {pathD && (
            <path
              d={pathD}
              fill="none"
              stroke="var(--accent)"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="graph-line"
            />
          )}

          {/* Data points */}
          {points.map((p, i) => (
            <circle
              key={i}
              cx={p.x}
              cy={p.y}
              r={i === points.length - 1 ? 5 : 3}
              fill={i === points.length - 1 ? "var(--accent)" : "var(--surface-1)"}
              stroke="var(--accent)"
              strokeWidth="2"
              className="graph-point"
            >
              <title>{formatDate(p.date)}: {formatGrams(p.weight)}g</title>
            </circle>
          ))}

          {/* X-axis labels */}
          {points.length > 0 && (
            <>
              <text
                x={graphPadding.left}
                y={graphHeight - 8}
                textAnchor="start"
                className="graph-label"
              >
                {formatDate(minDate)}
              </text>
              <text
                x={graphPadding.left + innerWidth}
                y={graphHeight - 8}
                textAnchor="end"
                className="graph-label"
              >
                {formatDate(maxDate)}
              </text>
            </>
          )}
        </svg>
      </div>

      {sortedHistory.length > 0 && (
        <div className="spool-detail-panel-history">
          <div className="spool-detail-panel-history-title">
            Usage History
            <button
              className={`btn-ghost btn-xs ${selectMode ? 'active' : ''}`}
              onClick={() => { setSelectMode(!selectMode); setSelectedIds(new Set()); setBulkProjectId(''); }}
            >
              {selectMode ? 'Cancel' : 'Select'}
            </button>
          </div>
          <div className="spool-detail-panel-history-list">
            {[...sortedHistory].reverse().slice(0, 10).map((entry, i) => (
              <div key={entry.id || i} className={`history-entry ${selectMode ? 'select-mode' : ''}`} style={{ animationDelay: `${i * 50}ms` }}>
                {selectMode && (
                  <input
                    type="checkbox"
                    className="history-checkbox"
                    checked={selectedIds.has(entry.id)}
                    onChange={() => {
                      setSelectedIds(prev => {
                        const next = new Set(prev);
                        if (next.has(entry.id)) next.delete(entry.id);
                        else next.add(entry.id);
                        return next;
                      });
                    }}
                  />
                )}
                <div className="history-entry-date">
                  {new Date(entry.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' })}
                </div>
                <div className="history-entry-amount">-{formatGrams(entry.weight_used)}g</div>
                <div className="history-entry-project">
                  {assigningEntryId === entry.id ? (
                    <select
                      className="history-project-select"
                      autoFocus
                      defaultValue={entry.project_id || ''}
                      onChange={e => handleAssignProject(entry.id, e.target.value ? parseInt(e.target.value) : null)}
                      onBlur={() => setAssigningEntryId(null)}
                    >
                      <option value="">No project</option>
                      {projects.map(p => (
                        <option key={p.id} value={p.id}>{p.name}</option>
                      ))}
                    </select>
                  ) : entry.project_name ? (
                    <button className="history-project-tag" onClick={() => !selectMode && setAssigningEntryId(entry.id)} title="Change project">
                      {entry.project_name}
                    </button>
                  ) : (
                    !selectMode && (
                      <button className="history-assign-btn" onClick={() => setAssigningEntryId(entry.id)} title="Assign to project">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
                          <line x1="12" y1="11" x2="12" y2="17"/><line x1="9" y1="14" x2="15" y2="14"/>
                        </svg>
                      </button>
                    )
                  )}
                </div>
              </div>
            ))}
          </div>
          {selectMode && selectedIds.size > 0 && (
            <div className="bulk-assign-toolbar">
              <select value={bulkProjectId} onChange={e => setBulkProjectId(e.target.value)} className="history-project-select">
                <option value="">No project (unassign)</option>
                {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
              <button className="btn-primary btn-sm" disabled={bulkAssigning} onClick={handleBulkAssign}>
                {bulkAssigning ? 'Assigning...' : `Assign ${selectedIds.size} entries`}
              </button>
            </div>
          )}
          {sortedHistory.length > 10 && (
            <div className="history-more">+ {sortedHistory.length - 10} more entries</div>
          )}
        </div>
      )}

      {sortedHistory.length === 0 && (
        <div className="spool-detail-panel-no-history">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <circle cx="12" cy="12" r="10"/>
            <path d="M12 6v6l4 2"/>
          </svg>
          <span>No usage history yet</span>
        </div>
      )}

      <div className="spool-detail-panel-actions">
        <button type="button" className="btn-primary" onClick={onRecordUsage}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 5v14M5 12h14"/>
          </svg>
          Record Usage
        </button>
        <button type="button" className="btn-ghost" onClick={onClose}>Close</button>
      </div>
    </div>
  );
}
