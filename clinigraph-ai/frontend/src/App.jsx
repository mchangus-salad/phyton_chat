/**
 * CliniGraph AI - Frontend App
 *
 * This is the main entry point for the CliniGraph AI frontend.
 *
 * GenAI Components Available:
 * - AgentQueryPanel: General medical queries (POST /api/v1/agent/query/)
 * - OncologyQueryPanel: Oncology research (POST /api/v1/agent/oncology/query/)
 * - MedicalQueryPanel: Domain-scoped queries (POST /api/v1/agent/medical/query/)
 * - PatientCaseAnalyzePanel: Patient analysis (POST /api/v1/agent/patient/analyze/)
 *
 * Each component includes:
 * - JWT authentication with tenant selection
 * - Form inputs (question, domain, file upload, etc.)
 * - Comprehensive error handling (401, 402, 403, 429, 400, 500+)
 * - Success display with citations and PHI redaction notices
 * - Special yellow/orange alert styling for HTTP 402 (Payment Required)
 *
 * To use these components, import and render them:
 * import { AgentQueryPanel } from './features/platform/components/AgentQueryPanel';
 *
 * Then add to JSX:
 * <AgentQueryPanel />
 *
 * See README_GENAI_COMPONENTS.md for full documentation.
 */

import { useAppSession } from './useAppSession';
import { AppShellProvider } from './AppShellContext';

// To add GenAI components, uncomment the imports below and add to JSX:
// import { AgentQueryPanel } from './features/platform/components/AgentQueryPanel';
// import { OncologyQueryPanel } from './features/platform/components/OncologyQueryPanel';
// import { MedicalQueryPanel } from './features/platform/components/MedicalQueryPanel';
// import { PatientCaseAnalyzePanel } from './features/platform/components/PatientCaseAnalyzePanel';

const productAreas = [
  {
    title: 'Clinical Workspace',
    description: 'History-aware medical reasoning, patient-case analysis, and citation-backed answers.',
  },
  {
    title: 'Trust and Compliance',
    description: 'HIPAA-safe de-identification, audit visibility, and tenant-aware access control.',
  },
  {
    title: 'Platform Operations',
    description: 'Billing, abuse telemetry, Prometheus metrics, and an enterprise-ready control plane.',
  },
];

const milestones = [
  'JWT authentication and tenant memberships',
  'Patient-case upload pipeline with PHI redaction',
  'Stripe checkout foundation and plan catalog',
  'Prometheus and Grafana observability stack',
];

function SessionTopbar({ session, credentials, setCredentials, login, logout, loading, error, isAuthenticated }) {
  if (isAuthenticated) {
    return (
      <div className="session-topbar">
        <span className="session-topbar__username">
          Signed in as <strong>{session.username}</strong>
          {session.tenantId && <span className="session-topbar__tenant"> · {session.tenantId.slice(0, 8)}&hellip;</span>}
        </span>
        <button type="button" className="session-topbar__logout" onClick={logout}>
          Sign out
        </button>
      </div>
    );
  }

  const handleSubmit = async (e) => {
    e.preventDefault();
    await login();
  };

  return (
    <div className="session-topbar session-topbar--login">
      <form className="session-topbar__form" onSubmit={handleSubmit}>
        <input
          type="text"
          className="session-topbar__input"
          placeholder="Username"
          value={credentials.username}
          onChange={(e) => setCredentials((c) => ({ ...c, username: e.target.value }))}
          autoComplete="username"
        />
        <input
          type="password"
          className="session-topbar__input"
          placeholder="Password"
          value={credentials.password}
          onChange={(e) => setCredentials((c) => ({ ...c, password: e.target.value }))}
          autoComplete="current-password"
        />
        <button type="submit" className="session-topbar__login-btn" disabled={loading}>
          {loading ? 'Signing in…' : 'Sign in'}
        </button>
        {error && <span className="session-topbar__error">{error}</span>}
      </form>
    </div>
  );
}

export default function App() {
  const appSession = useAppSession();
  const { session, credentials, setCredentials, login, logout, loading, error, isAuthenticated } = appSession;

  const shellValue = {
    session,
    isAuthenticated,
    logout,
    navigateTo: () => {},
  };

  return (
    <AppShellProvider value={shellValue}>
      <SessionTopbar
        session={session}
        credentials={credentials}
        setCredentials={setCredentials}
        login={login}
        logout={logout}
        loading={loading}
        error={error}
        isAuthenticated={isAuthenticated}
      />
      <main className="page-shell">
        <section className="hero-panel">
          <p className="eyebrow">CliniGraph AI</p>
          <h1>Medical intelligence built for clinical rigor and SaaS scale.</h1>
          <p className="hero-copy">
            This frontend scaffold is the entry point for the multi-tenant workspace: secure login,
            evidence search, patient-case workflows, subscription management, and operations visibility.
          </p>
          <div className="hero-actions">
            <a className="primary-action" href="/api/v1/health/">
              API health
            </a>
            <a className="secondary-action" href="/api/schema/swagger-ui/">
              Swagger UI
            </a>
          </div>
        </section>

        <section className="content-grid">
          {productAreas.map((area) => (
            <article className="feature-card" key={area.title}>
              <h2>{area.title}</h2>
              <p>{area.description}</p>
            </article>
          ))}
        </section>

        <section className="status-panel">
          <div>
            <p className="eyebrow">Current delivery</p>
            <h2>Foundation in place for the full product surface.</h2>
          </div>
          <ul>
            {milestones.map((milestone) => (
              <li key={milestone}>{milestone}</li>
            ))}
          </ul>
        </section>
      </main>
    </AppShellProvider>
  );
}
