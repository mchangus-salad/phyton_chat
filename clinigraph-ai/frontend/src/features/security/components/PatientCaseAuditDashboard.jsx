import { useEffect, useState } from 'react';
import { usePatientCaseAudit } from '../hooks/usePatientCaseAudit';

const DOMAIN_COLORS = ['#6c8ebf', '#82b366', '#d6a520', '#ae4132', '#9b59b6', '#1abc9c'];

function StatCard({ label, value, sub }) {
  return (
    <div className="pca-stat-card">
      <p className="pca-stat-value">{value}</p>
      <p className="pca-stat-label">{label}</p>
      {sub && <p className="pca-stat-sub">{sub}</p>}
    </div>
  );
}

function TopBar({ categories }) {
  if (!categories || Object.keys(categories).length === 0) return null;
  const sorted = Object.entries(categories).sort(([, a], [, b]) => b - a).slice(0, 8);
  const max = sorted[0]?.[1] || 1;
  return (
    <div className="pca-phi-bars">
      {sorted.map(([cat, count]) => (
        <div key={cat} className="pca-phi-bar-row">
          <span className="pca-phi-cat">{cat}</span>
          <div className="pca-phi-track">
            <div
              className="pca-phi-fill"
              style={{ width: `${Math.round((count / max) * 100)}%` }}
            />
          </div>
          <span className="pca-phi-count">{count}</span>
        </div>
      ))}
    </div>
  );
}

function DomainPills({ domains }) {
  if (!domains || Object.keys(domains).length === 0) return null;
  const sorted = Object.entries(domains).sort(([, a], [, b]) => b - a);
  return (
    <div className="pca-domain-pills">
      {sorted.map(([domain, count], i) => (
        <span
          key={domain}
          className="pca-domain-pill"
          style={{ borderColor: DOMAIN_COLORS[i % DOMAIN_COLORS.length] }}
        >
          {domain} <strong>{count}</strong>
        </span>
      ))}
    </div>
  );
}

export function PatientCaseAuditDashboard({ authToken, isStaff }) {
  const [days, setDays] = useState(30);
  const { data, loading, error, refresh } = usePatientCaseAudit({ authToken, days });

  useEffect(() => {
    if (isStaff && authToken) refresh();
  }, [isStaff, authToken, refresh]);

  if (!isStaff) {
    return (
      <div className="pca-dashboard pca-dashboard--locked">
        <p className="eyebrow">Patient-Case Audit</p>
        <p className="sec-muted">Staff access required.</p>
      </div>
    );
  }

  return (
    <div className="pca-dashboard panel-surface">
      <header className="sec-header">
        <div>
          <p className="eyebrow">Patient-Case Audit</p>
          <h3 className="sec-title">Patient Case Analysis Log</h3>
          <p className="sec-muted">No PHI stored — audit counters and metadata only.</p>
        </div>
        <div className="sec-header-actions">
          <select
            className="pca-days-select"
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            aria-label="Time window"
          >
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={60}>Last 60 days</option>
            <option value={90}>Last 90 days</option>
          </select>
          <button type="button" className="secondary-action" onClick={refresh} disabled={loading}>
            {loading ? 'Loading…' : 'Refresh'}
          </button>
        </div>
      </header>

      {error && <p className="sec-error">{error}</p>}

      {data && (
        <>
          <div className="pca-stats-row">
            <StatCard label="Total sessions" value={data.total_sessions} sub={`Last ${data.window_days} days`} />
            <StatCard label="PHI tokens redacted" value={data.total_redactions} />
            <StatCard
              label="PHI categories"
              value={Object.keys(data.redactions_by_category || {}).length}
            />
            <StatCard
              label="Active domains"
              value={Object.keys(data.sessions_by_domain || {}).length}
            />
          </div>

          <section className="pca-section">
            <h4 className="pca-section-title">Sessions by domain</h4>
            <DomainPills domains={data.sessions_by_domain} />
          </section>

          <section className="pca-section">
            <h4 className="pca-section-title">PHI categories detected</h4>
            <TopBar categories={data.redactions_by_category} />
          </section>

          {data.recent_sessions?.length > 0 && (
            <section className="pca-section">
              <h4 className="pca-section-title">Recent sessions</h4>
              <div className="sec-table-wrapper">
                <table className="sec-table">
                  <thead>
                    <tr>
                      <th>Session ID</th>
                      <th>Domain</th>
                      <th>Redactions</th>
                      <th>User</th>
                      <th>Timestamp</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.recent_sessions.map((s) => (
                      <tr key={s.session_id}>
                        <td className="sec-event-type">{s.session_id.slice(0, 8)}…</td>
                        <td>{s.domain}{s.subdomain ? ` / ${s.subdomain}` : ''}</td>
                        <td>
                          <span className={`sec-severity-badge ${s.redaction_count > 5 ? 'severity-high' : s.redaction_count > 0 ? 'severity-medium' : 'severity-low'}`}>
                            {s.redaction_count}
                          </span>
                        </td>
                        <td className="sec-ip">{s.user_id || '—'}</td>
                        <td className="sec-ts">
                          {s.created_at ? new Date(s.created_at).toLocaleString() : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </>
      )}

      {!data && !loading && !error && (
        <p className="sec-empty">Click Refresh to load audit data.</p>
      )}
    </div>
  );
}
