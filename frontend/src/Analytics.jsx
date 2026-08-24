import React, { useContext, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { AuthContext } from './AuthContext';
import SpoolSpinner from './components/SpoolSpinner';
import EmptyState from './components/EmptyState';
import useMetadata, { ANALYTICS_METADATA } from './hooks/useMetadata';

export default function Analytics() {
  const { authFetch } = useContext(AuthContext);
  const [history, setHistory] = useState([]);
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [spools, setSpools] = useState([]);
  const metadata = useMetadata(authFetch, ANALYTICS_METADATA, { auto: true });
  const [days, setDays] = useState(30);
  const [projectAnalytics, setProjectAnalytics] = useState({});

  // Project management state
  const [showProjectModal, setShowProjectModal] = useState(false);
  const [editingProject, setEditingProject] = useState(null);
  const [projectForm, setProjectForm] = useState({ name: '', description: '', status: 'active', budget_grams: '' });
  const [projectSaving, setProjectSaving] = useState(false);
  const [statusFilter, setStatusFilter] = useState('active');

  useEffect(() => {
    async function fetchData() {
      setLoading(true);
      setError('');
      try {
        const [hRes, pRes, sRes] = await Promise.all([
          authFetch('/api/spoolhistory/'),
          authFetch('/api/projects/'),
          authFetch('/api/spools/'),
        ]);
        // Parse each response individually to avoid Promise.all failure on single bad response
        const hData = hRes.ok ? await hRes.json().catch(() => ({})) : {};
        const pData = pRes.ok ? await pRes.json().catch(() => ({})) : {};
        const sData = sRes.ok ? await sRes.json().catch(() => ({})) : {};

        if (hRes.ok) setHistory(hData.history || []);
        else setError(hData.msg || 'Failed to load history.');
        if (pRes.ok) setProjects(pData.projects || []);
        if (sRes.ok) setSpools(sData.spools || []);
      } catch (err) {
        console.error('Analytics fetch error:', err);
        setError('Error connecting to server.');
      }
      setLoading(false);
    }
    fetchData();
  }, [authFetch]);

  // Derived maps
  const materialNameById = useMemo(
    () => Object.fromEntries(metadata.materials.map(m => [m.id, m.name])),
    [metadata.materials],
  );
  const colorNameById = useMemo(
    () => Object.fromEntries(metadata.colors.map(c => [c.id, c.name])),
    [metadata.colors],
  );
  const spoolById = useMemo(() => Object.fromEntries(spools.map(s => [s.id, s])), [spools]);

  const sinceDate = useMemo(() => {
    const d = new Date();
    d.setDate(d.getDate() - Number(days || 30));
    return d;
  }, [days]);

  const recentHistory = useMemo(() => {
    return (history || []).filter(h => h.date && new Date(h.date) >= sinceDate);
  }, [history, sinceDate]);

  // Usage by material type (PLA, PETG, TPU, etc.)
  const usageByMaterial = useMemo(() => {
    const by = {};
    for (const e of recentHistory) {
      const s = spoolById[e.spool_id];
      if (!s) continue;
      const m = materialNameById[s.material_id] || 'Other';
      by[m] = (by[m] || 0) + (e.weight_used || 0);
    }
    return Object.entries(by).sort((a, b) => b[1] - a[1]);
  }, [recentHistory, spoolById, materialNameById]);

  // Usage by day for chart
  const usageByDay = useMemo(() => {
    const by = {};
    for (const e of recentHistory) {
      const day = e.date ? new Date(e.date).toISOString().slice(0, 10) : 'unknown';
      by[day] = (by[day] || 0) + (e.weight_used || 0);
    }
    return Object.entries(by).sort((a, b) => a[0] < b[0] ? -1 : 1);
  }, [recentHistory]);

  // Usage by material and day for multi-line chart
  const usageByMaterialByDay = useMemo(() => {
    const by = {};
    for (const e of recentHistory) {
      const s = spoolById[e.spool_id];
      if (!s) continue;
      const m = materialNameById[s.material_id] || 'Other';
      const day = e.date ? new Date(e.date).toISOString().slice(0, 10) : 'unknown';
      if (!by[m]) by[m] = {};
      by[m][day] = (by[m][day] || 0) + (e.weight_used || 0);
    }
    return by;
  }, [recentHistory, spoolById, materialNameById]);

  const totalRecent = useMemo(() => usageByMaterial.reduce((s, [, v]) => s + v, 0), [usageByMaterial]);

  // Depletion forecast - spools running low
  const depletionForecast = useMemo(() => {
    const forecast = [];
    for (const spool of spools) {
      if (spool.weight_remaining <= 0) continue;
      const material = materialNameById[spool.material_id] || 'Unknown';
      const color = colorNameById[spool.color_id] || 'Unknown';

      // Calculate daily usage for this spool
      const spoolHistory = recentHistory.filter(h => h.spool_id === spool.id);
      const totalUsed = spoolHistory.reduce((sum, h) => sum + (h.weight_used || 0), 0);
      const daysInPeriod = Math.max(1, days);
      const dailyUsage = totalUsed / daysInPeriod;

      // Skip spools with no usage data - we can't forecast without history
      if (dailyUsage <= 0) continue;

      const daysRemaining = Math.round(spool.weight_remaining / dailyUsage);
      const percentage = Math.round((spool.weight_remaining / (spool.weight_start || 1000)) * 100);

      let status = 'ok';
      if (daysRemaining <= 7) status = 'critical';
      else if (daysRemaining <= 14) status = 'warning';

      forecast.push({
        id: spool.id,
        name: `${color} ${material}`,
        material,
        remaining: spool.weight_remaining,
        percentage,
        daysRemaining,
        status
      });
    }
    return forecast.sort((a, b) => a.daysRemaining - b.daysRemaining).slice(0, 6);
  }, [spools, materialNameById, colorNameById, recentHistory, days]);

  // Stats calculations
  const stats = useMemo(() => {
    const currentMonthUsage = totalRecent;
    const lowStockCount = depletionForecast.filter(d => d.status === 'critical' || d.status === 'warning').length;

    // Estimate cost (assume ~£25 per kg average)
    const estimatedCost = (currentMonthUsage / 1000) * 25;

    // Calculate average spool lifespan
    const avgLifespan = depletionForecast.length > 0
      ? Math.round(depletionForecast.reduce((sum, d) => sum + d.daysRemaining, 0) / depletionForecast.length)
      : 0;

    return {
      usedThisMonth: Math.round(currentMonthUsage),
      spentThisMonth: estimatedCost.toFixed(2),
      avgLifespan,
      needReorder: lowStockCount
    };
  }, [totalRecent, depletionForecast]);

  // Smart insights
  const insights = useMemo(() => {
    const result = [];

    // Most used material tip
    if (usageByMaterial.length > 0) {
      const [topMaterial, topUsage] = usageByMaterial[0];
      result.push({
        type: 'tip',
        icon: '💡',
        text: `**${topMaterial}** is your most-used material (${Math.round(topUsage)}g). Consider bulk ordering to save on costs.`
      });
    }

    // Low stock warnings
    const criticalSpools = depletionForecast.filter(d => d.status === 'critical');
    if (criticalSpools.length > 0) {
      const spool = criticalSpools[0];
      result.push({
        type: 'warning',
        icon: '⚠️',
        text: `**${spool.name}** will run out in ~${spool.daysRemaining} days at current usage rate.`
      });
    }

    // Usage trend
    if (usageByDay.length >= 7) {
      const recentDays = usageByDay.slice(-7);
      const olderDays = usageByDay.slice(-14, -7);
      if (olderDays.length > 0) {
        const recentAvg = recentDays.reduce((s, [, v]) => s + v, 0) / recentDays.length;
        const olderAvg = olderDays.reduce((s, [, v]) => s + v, 0) / olderDays.length;
        const change = olderAvg > 0 ? Math.round(((recentAvg - olderAvg) / olderAvg) * 100) : 0;
        if (Math.abs(change) > 20) {
          result.push({
            type: 'trend',
            icon: '📊',
            text: `Usage is **${change > 0 ? 'up' : 'down'} ${Math.abs(change)}%** compared to last week. ${change > 0 ? 'Working on a big project?' : 'Taking a break?'}`
          });
        }
      }
    }

    // Weekend printing pattern
    const weekendUsage = recentHistory.filter(h => {
      const day = new Date(h.date).getDay();
      return day === 0 || day === 6;
    }).reduce((s, h) => s + (h.weight_used || 0), 0);
    const weekdayUsage = totalRecent - weekendUsage;
    if (weekendUsage > weekdayUsage * 0.6 && totalRecent > 100) {
      result.push({
        type: 'tip',
        icon: '🎯',
        text: `You tend to print more on **weekends**. Stock up by Friday!`
      });
    }

    return result.slice(0, 4);
  }, [usageByMaterial, depletionForecast, usageByDay, recentHistory, totalRecent]);

  // Chart data for SVG
  const chartData = useMemo(() => {
    const width = 520;
    const height = 160;
    const pad = { top: 20, right: 20, bottom: 30, left: 45 };

    const allDays = [...new Set(Object.values(usageByMaterialByDay).flatMap(m => Object.keys(m)))].sort();
    if (allDays.length === 0) return null;

    // Warm, Workshop-harmonised categorical palette (amber-led, one cool anchor
    // for legibility) instead of the old generic SaaS cyan/emerald/rose.
    const materialColors = {
      'PLA': '#ff7a18',
      'PETG': '#5ea3b0',
      'TPU': '#ffb02e',
      'ABS': '#e0594f',
      'Other': '#9ca3af'
    };

    const maxY = Math.max(10, ...Object.values(usageByMaterialByDay).flatMap(m => Object.values(m)));
    const toX = (idx) => pad.left + (idx / Math.max(1, allDays.length - 1)) * (width - pad.left - pad.right);
    const toY = (val) => height - pad.bottom - (val / maxY) * (height - pad.top - pad.bottom);

    const lines = {};
    for (const [material, dayData] of Object.entries(usageByMaterialByDay)) {
      const points = allDays.map((day, idx) => ({
        x: toX(idx),
        y: toY(dayData[day] || 0),
        value: dayData[day] || 0,
        day
      }));
      lines[material] = {
        points,
        color: materialColors[material] || materialColors['Other'],
        path: points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ')
      };
    }

    // Get month labels
    const monthLabels = [];
    let lastMonth = '';
    allDays.forEach((day, idx) => {
      const month = new Date(day).toLocaleDateString('en-US', { month: 'short' });
      if (month !== lastMonth) {
        monthLabels.push({ label: month, x: toX(idx) });
        lastMonth = month;
      }
    });

    return { width, height, pad, lines, toY, maxY, monthLabels };
  }, [usageByMaterialByDay]);

  const formatText = (text) => {
    return text.split('**').map((part, i) =>
      i % 2 === 1 ? <strong key={i}>{part}</strong> : part
    );
  };

  // Project CRUD handlers
  const openCreateProject = () => {
    setProjectForm({ name: '', description: '', status: 'active', budget_grams: '' });
    setEditingProject(null);
    setShowProjectModal(true);
  };

  const openEditProject = (project) => {
    setProjectForm({
      name: project.name,
      description: project.description || '',
      status: project.status || 'active',
      budget_grams: project.budget_grams != null ? String(project.budget_grams) : ''
    });
    setEditingProject(project);
    setShowProjectModal(true);
  };

  const closeProjectModal = () => {
    setShowProjectModal(false);
    setEditingProject(null);
    setProjectForm({ name: '', description: '', status: 'active', budget_grams: '' });
  };

  const handleProjectSubmit = async (e) => {
    e.preventDefault();
    if (!projectForm.name.trim()) return;
    setProjectSaving(true);

    try {
      const payload = {
        ...projectForm,
        budget_grams: projectForm.budget_grams ? parseFloat(projectForm.budget_grams) : null
      };
      if (editingProject) {
        // Update existing project
        const res = await authFetch(`/api/projects/${editingProject.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        if (res.ok) {
          const data = await res.json();
          setProjects(prev => prev.map(p => p.id === data.id ? { ...p, ...data } : p));
          closeProjectModal();
        }
      } else {
        // Create new project
        const res = await authFetch('/api/projects/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        if (res.ok) {
          const data = await res.json();
          setProjects(prev => [...prev, data]);
          closeProjectModal();
        }
      }
    } catch (err) {
      console.error('Project save error:', err);
    }
    setProjectSaving(false);
  };

  const handleDeleteProject = async (projectId) => {
    if (!window.confirm('Delete this project? Usage history will be kept but unlinked from the project.')) return;
    try {
      const res = await authFetch(`/api/projects/${projectId}`, { method: 'DELETE' });
      if (res.ok) {
        setProjects(prev => prev.filter(p => p.id !== projectId));
        // Clear analytics for deleted project
        setProjectAnalytics(prev => {
          const next = { ...prev };
          delete next[projectId];
          return next;
        });
      }
    } catch (err) {
      console.error('Project delete error:', err);
    }
  };

  if (loading || metadata.loading) {
    return (
      <div className="analytics-page">
        <SpoolSpinner label="Loading analytics…" />
      </div>
    );
  }

  return (
    <div className="analytics-page">
      {/* Page Header */}
      <div className="analytics-header">
        <div>
          <h2 className="analytics-title">Analytics</h2>
          <p className="analytics-subtitle">Insights into your filament usage and spending</p>
        </div>
        <select
          className="time-filter"
          value={days}
          onChange={e => setDays(Number(e.target.value))}
        >
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
          <option value={365}>Last year</option>
        </select>
      </div>

      {error && <div className="analytics-error">{error}</div>}

      {/* Stats Grid */}
      <div className="analytics-stats-grid">
        <div className="analytics-stat-card">
          <div className="stat-header">
            <div className="stat-icon cyan">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M16.5 9.4l-9-5.19M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/>
              </svg>
            </div>
          </div>
          <div className="stat-value">{stats.usedThisMonth}<span>g</span></div>
          <div className="stat-label">Used ({days}d)</div>
        </div>

        <div className="analytics-stat-card">
          <div className="stat-header">
            <div className="stat-icon green">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/>
              </svg>
            </div>
          </div>
          <div className="stat-value">£{stats.spentThisMonth}</div>
          <div className="stat-label">Est. cost ({days}d)</div>
        </div>

        <div className="analytics-stat-card">
          <div className="stat-header">
            <div className="stat-icon amber">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
              </svg>
            </div>
          </div>
          <div className="stat-value">{stats.avgLifespan}<span> days</span></div>
          <div className="stat-label">Avg remaining</div>
        </div>

        <div className="analytics-stat-card">
          <div className="stat-header">
            <div className="stat-icon rose">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
              </svg>
            </div>
          </div>
          <div className="stat-value">{stats.needReorder}</div>
          <div className="stat-label">Need reorder</div>
        </div>
      </div>

      {/* Main Content Grid */}
      <div className="analytics-content-grid">
        {/* Charts Column */}
        <div className="analytics-charts-column">
          {/* Usage Trends Chart */}
          <div className="analytics-card">
            <div className="card-header">
              <h3 className="card-title">
                <span className="card-title-icon cyan">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
                  </svg>
                </span>
                Usage Trends
              </h3>
            </div>
            <div className="card-body">
              {chartData ? (
                <>
                  <svg width="100%" viewBox={`0 0 ${chartData.width} ${chartData.height}`} className="analytics-chart">
                    {/* Grid lines */}
                    {[0.25, 0.5, 0.75, 1].map((pct, i) => (
                      <line
                        key={i}
                        x1={chartData.pad.left}
                        y1={chartData.toY(chartData.maxY * pct)}
                        x2={chartData.width - chartData.pad.right}
                        y2={chartData.toY(chartData.maxY * pct)}
                        stroke="var(--border, #374151)"
                        strokeOpacity="0.3"
                      />
                    ))}

                    {/* Y-axis labels */}
                    <text x={chartData.pad.left - 8} y={chartData.toY(chartData.maxY)} fontSize="10" fill="var(--text-muted, #9ca3af)" textAnchor="end" dominantBaseline="middle">
                      {Math.round(chartData.maxY)}g
                    </text>
                    <text x={chartData.pad.left - 8} y={chartData.toY(chartData.maxY * 0.5)} fontSize="10" fill="var(--text-muted, #9ca3af)" textAnchor="end" dominantBaseline="middle">
                      {Math.round(chartData.maxY * 0.5)}g
                    </text>

                    {/* Month labels */}
                    {chartData.monthLabels.map((m, i) => (
                      <text key={i} x={m.x} y={chartData.height - 10} fontSize="10" fill="var(--text-muted, #9ca3af)" textAnchor="middle">
                        {m.label}
                      </text>
                    ))}

                    {/* Lines */}
                    {Object.entries(chartData.lines).map(([material, data]) => (
                      <g key={material}>
                        <path
                          d={data.path}
                          fill="none"
                          stroke={data.color}
                          strokeWidth="2.5"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          className="chart-line-animated"
                        />
                        {data.points.map((p, i) => (
                          <circle
                            key={i}
                            cx={p.x}
                            cy={p.y}
                            r="3"
                            fill="var(--background, #0a0f1a)"
                            stroke={data.color}
                            strokeWidth="2"
                          />
                        ))}
                      </g>
                    ))}
                  </svg>
                  <div className="chart-legend">
                    {Object.entries(chartData.lines).map(([material, data]) => (
                      <div key={material} className="legend-item">
                        <span className="legend-dot" style={{ background: data.color }}></span>
                        {material}
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <div className="chart-empty">No usage data available for this period.</div>
              )}
            </div>
          </div>

          {/* Cost Breakdown */}
          <div className="analytics-card">
            <div className="card-header">
              <h3 className="card-title">
                <span className="card-title-icon green">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M21.21 15.89A10 10 0 118 2.83"/><path d="M22 12A10 10 0 0012 2v10z"/>
                  </svg>
                </span>
                Cost Breakdown
              </h3>
            </div>
            <div className="card-body">
              {usageByMaterial.length > 0 ? (
                <>
                  <div className="cost-bars">
                    {usageByMaterial.slice(0, 5).map(([material, grams]) => {
                      const pct = Math.round((grams / totalRecent) * 100);
                      const cost = ((grams / 1000) * 25).toFixed(2);
                      const colorMap = { 'PLA': '#ff7a18', 'PETG': '#5ea3b0', 'TPU': '#ffb02e', 'ABS': '#e0594f' };
                      const color = colorMap[material] || '#9ca3af';
                      return (
                        <div key={material} className="cost-item">
                          <span className="cost-label">{material}</span>
                          <div className="cost-bar-container">
                            <div
                              className="cost-bar"
                              style={{ width: `${pct}%`, background: `linear-gradient(90deg, ${color}, ${color}dd)` }}
                            >
                              <span className="cost-bar-label">{pct}%</span>
                            </div>
                          </div>
                          <span className="cost-value">£{cost}</span>
                        </div>
                      );
                    })}
                  </div>
                  <div className="cost-summary">
                    <div className="cost-total">Total: <strong>£{stats.spentThisMonth}</strong></div>
                    <div className="cost-total">Avg: <strong>£{(totalRecent > 0 ? (parseFloat(stats.spentThisMonth) / (totalRecent / 1000)).toFixed(2) : '0.00')}</strong>/kg</div>
                  </div>
                </>
              ) : (
                <div className="chart-empty">No cost data available.</div>
              )}
            </div>
          </div>
        </div>

        {/* Smart Insights */}
        <div className="analytics-card insights-card">
          <div className="card-header">
            <h3 className="card-title">
              <span className="card-title-icon amber">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
                </svg>
              </span>
              Smart Insights
            </h3>
            <span className="ai-badge">✨ AI</span>
          </div>
          <div className="card-body">
            {insights.length > 0 ? (
              <div className="insights-list">
                {insights.map((insight, i) => (
                  <div key={i} className="insight-item">
                    <div className="insight-header">
                      <span className="insight-icon">{insight.icon}</span>
                      <span className={`insight-type ${insight.type}`}>{insight.type}</span>
                    </div>
                    <p className="insight-text">{formatText(insight.text)}</p>
                  </div>
                ))}
              </div>
            ) : (
              <div className="chart-empty">Add more usage data to get personalized insights.</div>
            )}
            <div className="insights-cta">
              <button className="insights-cta-btn" disabled>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
                </svg>
                Get More Insights
                <span className="ai-badge">Claude</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Depletion Forecast */}
      <div className="analytics-card depletion-card">
        <div className="card-header">
          <h3 className="card-title">
            <span className="card-title-icon rose">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
              </svg>
            </span>
            Depletion Forecast
          </h3>
        </div>
        <div className="card-body">
          {depletionForecast.length > 0 ? (
            <div className="depletion-list">
              {depletionForecast.map((item) => (
                <div key={item.id} className={`depletion-item ${item.status}`}>
                  <div className={`depletion-status ${item.status}`}>
                    {item.status === 'critical' ? (
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
                      </svg>
                    ) : item.status === 'warning' ? (
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
                      </svg>
                    ) : (
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
                      </svg>
                    )}
                  </div>
                  <div className="depletion-info">
                    <div className="depletion-name">
                      {item.name}
                      <span className="depletion-material">{item.material}</span>
                    </div>
                    <div className="depletion-bar-container">
                      <div className={`depletion-bar ${item.status}`} style={{ width: `${Math.min(100, item.percentage)}%` }}></div>
                    </div>
                  </div>
                  <div className="depletion-meta">
                    <div className="depletion-remaining">{Math.round(item.remaining)}g</div>
                    <div className={`depletion-days ${item.status}`}>
                      ~{item.daysRemaining > 365 ? '1yr+' : `${item.daysRemaining} days`}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="chart-empty">No usage data in this period to forecast from.</div>
          )}
        </div>
      </div>

      {/* Print History Teaser */}
      <div className="analytics-card print-history-card">
        <div className="card-header">
          <h3 className="card-title">
            <span className="card-title-icon cyan">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M6 9H4.5a2.5 2.5 0 010-5H6"/><path d="M18 9h1.5a2.5 2.5 0 000-5H18"/><path d="M4 22h16"/><path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22"/><path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22"/><path d="M18 2H6v7a6 6 0 0012 0V2Z"/>
              </svg>
            </span>
            Print History
          </h3>
          <span className="coming-badge">Coming Soon</span>
        </div>
        <div className="card-body">
          <div className="print-history-teaser">
            <p>Connect your printer to automatically track filament usage per print</p>
            <div className="printer-grid">
              <div className="printer-card">
                <div className="printer-icon">🖨️</div>
                <div className="printer-name">Bambu Lab</div>
                <div className="printer-status">Coming Soon →</div>
              </div>
              <div className="printer-card">
                <div className="printer-icon">🔧</div>
                <div className="printer-name">Prusa Connect</div>
                <div className="printer-status planned">Planned</div>
              </div>
              <div className="printer-card">
                <div className="printer-icon">🐙</div>
                <div className="printer-name">OctoPrint</div>
                <div className="printer-status planned">Planned</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Projects Section */}
      <div className="analytics-card">
        <div className="card-header">
          <h3 className="card-title">
            <span className="card-title-icon green">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
              </svg>
            </span>
            Projects
          </h3>
          <div className="card-header-actions">
            <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className="status-filter">
              <option value="all">All</option>
              <option value="active">Active</option>
              <option value="completed">Completed</option>
              <option value="archived">Archived</option>
            </select>
            <button className="btn-primary btn-sm" onClick={openCreateProject}>
              + New Project
            </button>
          </div>
        </div>
        <div className="card-body">
          {(() => {
            const filtered = projects.filter(p => statusFilter === 'all' || (p.status || 'active') === statusFilter);
            return filtered.length > 0 ? (
              <div className="projects-list">
                {filtered.map(p => (
                  <div key={p.id} className="project-item">
                    <div className="project-content">
                      <div className="project-header">
                        <Link to={`/projects/${p.id}`} className="project-link"><strong>{p.name}</strong></Link>
                        <span className={`project-status-badge status-${p.status || 'active'}`}>
                          {p.status || 'active'}
                        </span>
                        {p.description && <span className="project-desc">{p.description}</span>}
                      </div>
                      <div className="project-meta">
                        {(() => {
                          const a = projectAnalytics[p.id];
                          if (!a) {
                            authFetch(`/api/projects/${p.id}/analytics?days=9999`).then(async (aRes) => {
                              if (aRes.ok) {
                                const aData = await aRes.json();
                                setProjectAnalytics(pa => ({ ...pa, [p.id]: aData }));
                              }
                            }).catch(() => {});
                            return <span>Loading...</span>;
                          }
                          return (
                            <span>
                              {Math.round(a.total_grams)}g • Est £{a.estimated_cost.toFixed(2)} • {a.entry_count} entries
                            </span>
                          );
                        })()}
                      </div>
                      {p.budget_grams && projectAnalytics[p.id] && (
                        <div className="budget-progress">
                          <div className="budget-progress-bar">
                            <div
                              className={`budget-progress-fill ${
                                (projectAnalytics[p.id].total_grams / p.budget_grams) > 1 ? 'over-budget' :
                                (projectAnalytics[p.id].total_grams / p.budget_grams) > 0.8 ? 'near-budget' : ''
                              }`}
                              style={{ width: `${Math.min(100, (projectAnalytics[p.id].total_grams / p.budget_grams) * 100)}%` }}
                            />
                          </div>
                          <span className="budget-progress-label">
                            {Math.round(projectAnalytics[p.id].total_grams)}g / {p.budget_grams}g
                            ({Math.round((projectAnalytics[p.id].total_grams / p.budget_grams) * 100)}%)
                          </span>
                        </div>
                      )}
                    </div>
                    <div className="project-actions">
                      <button className="btn-ghost btn-sm" onClick={() => openEditProject(p)}>Edit</button>
                      <button className="btn-danger btn-sm" onClick={() => handleDeleteProject(p.id)}>Delete</button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              projects.length > 0 ? (
                <EmptyState
                  title={`No ${statusFilter} projects`}
                  message="Try a different status filter to see more."
                />
              ) : (
                <EmptyState
                  title="No projects yet"
                  message="Create one to track filament cost and usage per print job."
                  actionLabel="Create your first project"
                  onAction={openCreateProject}
                />
              )
            );
          })()}
        </div>
      </div>

      {/* Project Modal */}
      {showProjectModal && (
        <div className="modal-overlay" onClick={closeProjectModal}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h3>{editingProject ? 'Edit Project' : 'New Project'}</h3>
              <button className="modal-close" onClick={closeProjectModal}>×</button>
            </div>
            <form onSubmit={handleProjectSubmit}>
              <div className="modal-body">
                <label className="form-group">
                  <span>Project Name</span>
                  <input
                    type="text"
                    value={projectForm.name}
                    onChange={e => setProjectForm(f => ({ ...f, name: e.target.value }))}
                    placeholder="e.g., Benchy Fleet, Phone Stand"
                    required
                    autoFocus
                  />
                </label>
                <label className="form-group">
                  <span>Description (optional)</span>
                  <textarea
                    value={projectForm.description}
                    onChange={e => setProjectForm(f => ({ ...f, description: e.target.value }))}
                    placeholder="Notes about this project..."
                    rows={3}
                  />
                </label>
                <div className="form-row">
                  <label className="form-group">
                    <span>Status</span>
                    <select value={projectForm.status} onChange={e => setProjectForm(f => ({ ...f, status: e.target.value }))}>
                      <option value="active">Active</option>
                      <option value="completed">Completed</option>
                      <option value="archived">Archived</option>
                    </select>
                  </label>
                  <label className="form-group">
                    <span>Budget (grams, optional)</span>
                    <input
                      type="number"
                      value={projectForm.budget_grams}
                      onChange={e => setProjectForm(f => ({ ...f, budget_grams: e.target.value }))}
                      placeholder="e.g., 500"
                      min="0"
                      step="1"
                    />
                  </label>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn-ghost" onClick={closeProjectModal}>Cancel</button>
                <button type="submit" className="btn-primary" disabled={projectSaving || !projectForm.name.trim()}>
                  {projectSaving ? 'Saving...' : (editingProject ? 'Save Changes' : 'Create Project')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
