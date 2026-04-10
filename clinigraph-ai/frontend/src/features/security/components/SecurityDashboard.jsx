import { useEffect } from 'react';
import { useSecurityEvents } from '../hooks/useSecurityEvents';

const SEVERITY_TONE = {
  critical: 'severity-critical',
  high: 'severity-high',
  medium: 'severity-medium',
  low: 'severity-low',
};

function SeverityBadge({ severity }) {
  const cls = SEVERITY_TONE[severity?.toLowerCase()] || 'severity-low';
  return <span className={`sec-severity-badge ${cls}`}>{severity || 'unknown'}</span>;
}

export function SecurityDashboard({ authToken, isStaff }) {
  const { events, loading, error, loadedAt, refresh } = useSecurityEvents({ authToken });

  useEffect(() => {
    if (isStaff && authToken) {
      refresh();
    }
  }, [isStaff, authToken, refresh]);

  if (!isStaff) {
    return (
      <div className="sec-dashboard sec-dashboard--locked">
        <p className="eyebrow">Security Audit</p>
        <h3>Staff access required</h3>
        <p className="sec-muted">Only staff accounts can view security event logs.</p>
      </div>
    );
  }

  const criticalCount = events.filter((e) => e.severity?.toLowerCase() === 'critical').length;
  const highCount = events.filter((e) => e.severity?.toLowerCase() === 'high').length;

  return (
    <div className="sec-dashboard panel-surface">
      <header className="sec-header">
        <div>
          <p className="eyebrow">Security Audit</p>
          <h3 className="sec-title">Security Event Log</h3>
          {loadedAt && (
            <p className="sec-muted">Last loaded: {loadedAt.toLocaleTimeString()}</p>
          )}
        </div>
        <div className="sec-header-actions">
          <div className="sec-summary-pills">
            {criticalCount > 0 && (
              <span className="sec-pill sec-pill--critical">{criticalCount} critical</span>
            )}
            {highCount > 0 && (
              <span className="sec-pill sec-pill--high">{highCount} high</span>
            )}
            <span className="sec-pill sec-pill--total">{events.length} total</span>
          </div>
          <button
            type="button"
            className="secondary-action"
            onClick={refresh}
            disabled={loading}
          >
            {loading ? 'Loading…' : 'Refresh'}
          </button>
        </div>
      </header>

      {error && <p className="sec-error">{error}</p>}

      {!error && events.length === 0 && !loading && (
        <p className="sec-empty">No security events recorded yet. Click Refresh to load.</p>
      )}

      {events.length > 0 && (
        <div className="sec-table-wrapper">
          <table className="sec-table">
            <thead>
              <tr>
                <th>Severity</th>
                <th>Event Type</th>
                <th>Method</th>
                <th>Path</th>
                <th>IP Address</th>
                <th>Timestamp</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event, index) => (
                <tr
                  key={`${event.created_at}-${index}`}
                  className={`sec-row ${event.severity?.toLowerCase() === 'critical' ? 'sec-row--critical' : ''}`}
                >
                  <td><SeverityBadge severity={event.severity} /></td>
                  <td className="sec-event-type">{event.event_type}</td>
                  <td><code className="sec-method">{event.method || '—'}</code></td>
                  <td className="sec-path" title={event.path}>{event.path || '—'}</td>
                  <td className="sec-ip">{event.ip_address || '—'}</td>
                  <td className="sec-ts">
                    {event.created_at
                      ? new Date(event.created_at).toLocaleString()
                      : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
