import React, { useContext, useEffect, useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { AuthContext } from './AuthContext';
import SpoolSpinner from './components/SpoolSpinner';

export default function ProjectDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { authFetch } = useContext(AuthContext);
  const [project, setProject] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    async function fetchData() {
      setLoading(true);
      setError('');
      try {
        const [pRes, aRes] = await Promise.all([
          authFetch(`/api/projects/${id}`),
          authFetch(`/api/projects/${id}/analytics?days=9999`)
        ]);
        if (!cancelled) {
          if (pRes.ok) setProject(await pRes.json());
          else setError('Project not found');
          if (aRes.ok) setAnalytics(await aRes.json());
        }
      } catch {
        if (!cancelled) setError('Error loading project');
      }
      if (!cancelled) setLoading(false);
    }
    fetchData();
    return () => { cancelled = true; };
  }, [id, authFetch]);

  const handleDelete = async () => {
    if (!window.confirm('Delete this project? Usage history will be kept but unlinked.')) return;
    try {
      const res = await authFetch(`/api/projects/${id}`, { method: 'DELETE' });
      if (res.ok) navigate('/analytics');
    } catch (e) {
      console.error('Delete failed:', e);
    }
  };

  if (loading) {
    return (
      <div className="project-detail-page">
        <SpoolSpinner label="Loading project…" />
      </div>
    );
  }

  if (error || !project) {
    return (
      <div className="project-detail-page">
        <div className="project-detail-error">
          <p>{error || 'Project not found'}</p>
          <Link to="/analytics" className="btn-ghost">Back to Analytics</Link>
        </div>
      </div>
    );
  }

  const budgetPct = project.budget_grams && analytics
    ? (analytics.total_grams / project.budget_grams) * 100
    : null;

  return (
    <div className="project-detail-page">
      {/* Header */}
      <div className="project-detail-header">
        <Link to="/analytics" className="project-detail-back">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
          Analytics
        </Link>
        <div className="project-detail-title-row">
          <div>
            <h1 className="project-detail-name">{project.name}</h1>
            {project.description && <p className="project-detail-desc">{project.description}</p>}
          </div>
          <div className="project-detail-title-meta">
            <span className={`project-status-badge status-${project.status || 'active'}`}>
              {project.status || 'active'}
            </span>
            {project.created_at && (
              <span className="project-detail-date">
                Created {new Date(project.created_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Stats */}
      {analytics && (
        <div className="project-detail-stats">
          <div className="project-stat-card">
            <div className="project-stat-value">{Math.round(analytics.total_grams)}g</div>
            <div className="project-stat-label">Filament Used</div>
          </div>
          <div className="project-stat-card">
            <div className="project-stat-value">&pound;{analytics.estimated_cost.toFixed(2)}</div>
            <div className="project-stat-label">Est. Total Cost</div>
          </div>
          <div className="project-stat-card">
            <div className="project-stat-value">{analytics.entry_count}</div>
            <div className="project-stat-label">Filament Entries</div>
          </div>
          {(analytics.bits_total_used > 0 || analytics.bits_entry_count > 0) && (
            <>
              <div className="project-stat-card">
                <div className="project-stat-value">{analytics.bits_total_used || 0}</div>
                <div className="project-stat-label">Bits Used</div>
              </div>
              <div className="project-stat-card">
                <div className="project-stat-value">&pound;{(analytics.bits_estimated_cost || 0).toFixed(2)}</div>
                <div className="project-stat-label">Bits Cost</div>
              </div>
            </>
          )}
        </div>
      )}

      {/* Budget Progress */}
      {project.budget_grams && analytics && (
        <div className="analytics-card">
          <div className="card-header">
            <h3 className="card-title">Budget</h3>
          </div>
          <div className="card-body">
            <div className="budget-progress">
              <div className="budget-progress-bar budget-progress-bar-lg">
                <div
                  className={`budget-progress-fill ${budgetPct > 100 ? 'over-budget' : budgetPct > 80 ? 'near-budget' : ''}`}
                  style={{ width: `${Math.min(100, budgetPct)}%` }}
                />
              </div>
              <span className="budget-progress-label">
                {Math.round(analytics.total_grams)}g / {project.budget_grams}g ({Math.round(budgetPct)}%)
                {budgetPct > 100 && <strong className="over-budget-text"> — Over budget</strong>}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Materials Breakdown */}
      {analytics && analytics.materials && analytics.materials.length > 0 && (
        <div className="analytics-card">
          <div className="card-header">
            <h3 className="card-title">Materials Used</h3>
          </div>
          <div className="card-body">
            <div className="materials-breakdown">
              {analytics.materials.map((m, i) => {
                const maxGrams = analytics.materials[0].grams;
                return (
                  <div key={i} className="material-row">
                    <div className="material-name">{m.material}</div>
                    <div className="material-bar-container">
                      <div
                        className="material-bar"
                        style={{ width: `${(m.grams / maxGrams) * 100}%` }}
                      />
                    </div>
                    <div className="material-stats">
                      <span>{Math.round(m.grams)}g</span>
                      {m.cost > 0 && <span className="material-cost">&pound;{m.cost.toFixed(2)}</span>}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Bits Breakdown */}
      {analytics && analytics.bits_breakdown && analytics.bits_breakdown.length > 0 && (
        <div className="analytics-card">
          <div className="card-header">
            <h3 className="card-title">Bits Used</h3>
          </div>
          <div className="card-body">
            <div className="materials-breakdown">
              {analytics.bits_breakdown.map((b, i) => {
                const maxCount = analytics.bits_breakdown[0].count;
                return (
                  <div key={i} className="material-row">
                    <div className="material-name">{b.category}</div>
                    <div className="material-bar-container">
                      <div
                        className="material-bar"
                        style={{ width: `${(b.count / maxCount) * 100}%`, background: 'var(--color-accent, #5ba85b)' }}
                      />
                    </div>
                    <div className="material-stats">
                      <span>{b.count} pcs</span>
                      {b.cost > 0 && <span className="material-cost">&pound;{b.cost.toFixed(2)}</span>}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Usage Timeline */}
      {analytics && analytics.timeline && analytics.timeline.length > 0 && (
        <div className="analytics-card">
          <div className="card-header">
            <h3 className="card-title">Usage Timeline</h3>
          </div>
          <div className="card-body">
            <div className="project-timeline">
              {analytics.timeline.map((t, i) => (
                <div key={i} className="timeline-entry">
                  <div className="timeline-date">
                    {new Date(t.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' })}
                  </div>
                  <div className="timeline-grams">{Math.round(t.grams)}g</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="project-detail-actions">
        <a
          href={`/api/projects/${id}/export.csv`}
          className="btn-primary"
          target="_blank"
          rel="noopener noreferrer"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/>
          </svg>
          Export CSV
        </a>
        <button className="btn-danger" onClick={handleDelete}>Delete Project</button>
      </div>
    </div>
  );
}
