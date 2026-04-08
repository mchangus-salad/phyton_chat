/**
 * CliniGraph AI - Frontend App
 *
 * Entry point for the multi-tenant workspace.
 * Routing is handled via RouterProvider (state-based, no library dependency).
 *
 * Routes:
 *  home     – Marketing / landing page
 *  login    – Full-page sign-in form
 *  signup   – Full-page account creation form
 *  billing  – Billing dashboard (auth required)
 *  workspace – Clinical workspace shell (auth required)
 *
 * GenAI Components Available:
 * - AgentQueryPanel: General medical queries (POST /api/v1/agent/query/)
 * - OncologyQueryPanel: Oncology research (POST /api/v1/agent/oncology/query/)
 * - MedicalQueryPanel: Domain-scoped queries (POST /api/v1/agent/medical/query/)
 * - PatientCaseAnalyzePanel: Patient analysis (POST /api/v1/agent/patient/analyze/)
 */

import { useEffect } from 'react';
import { useAppSession } from './useAppSession';
import { AppShellProvider } from './AppShellContext';
import { RouterProvider, ROUTES, useRouter } from './RouterContext';
import { LoginPage } from '../features/auth/components/LoginPage';
import { SignupPage } from '../features/auth/components/SignupPage';
import { BillingPage } from '../features/billing/components/BillingPage';

// To add GenAI components, uncomment and use in WorkspacePage:
// import { AgentQueryPanel } from './features/platform/components/AgentQueryPanel';

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
  'Login / signup / billing pages',
];

// ---------------------------------------------------------------------------
// Top navigation bar
// ---------------------------------------------------------------------------

function Topbar({ session, isAuthenticated, logout }) {
  const { navigate, route } = useRouter();

  return (
    <header className="topbar">
      <button
        type="button"
        className="topbar__brand"
        onClick={() => navigate(ROUTES.HOME)}
      >
        CliniGraph AI
      </button>

      <nav className="topbar__nav" aria-label="Main navigation">
        {isAuthenticated ? (
          <>
            <button
              type="button"
              className={`topbar__nav-link${route === ROUTES.BILLING ? ' topbar__nav-link--active' : ''}`}
              onClick={() => navigate(ROUTES.BILLING)}
            >
              Billing
            </button>
            <span className="topbar__username">{session.username}</span>
            <button type="button" className="topbar__btn topbar__btn--secondary" onClick={logout}>
              Sign out
            </button>
          </>
        ) : (
          <>
            <button
              type="button"
              className={`topbar__nav-link${route === ROUTES.LOGIN ? ' topbar__nav-link--active' : ''}`}
              onClick={() => navigate(ROUTES.LOGIN)}
            >
              Sign in
            </button>
            <button
              type="button"
              className="topbar__btn topbar__btn--primary"
              onClick={() => navigate(ROUTES.SIGNUP)}
            >
              Get started
            </button>
          </>
        )}
      </nav>
    </header>
  );
}

// ---------------------------------------------------------------------------
// Home / landing page
// ---------------------------------------------------------------------------

function HomePage() {
  const { navigate } = useRouter();

  return (
    <main className="page-shell">
      <section className="hero-panel">
        <p className="eyebrow">CliniGraph AI</p>
        <h1>Medical intelligence built for clinical rigor and SaaS scale.</h1>
        <p className="hero-copy">
          The multi-tenant workspace for clinical decision support: secure login,
          evidence search, patient-case workflows, subscription management, and operations visibility.
        </p>
        <div className="hero-actions">
          <button className="primary-action" onClick={() => navigate(ROUTES.SIGNUP)}>
            Create account
          </button>
          <button className="secondary-action" onClick={() => navigate(ROUTES.LOGIN)}>
            Sign in
          </button>
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
  );
}

// ---------------------------------------------------------------------------
// Workspace shell (post-login landing)
// ---------------------------------------------------------------------------

function WorkspacePage() {
  const { session } = useAppShell_inner();
  const { navigate } = useRouter();

  return (
    <main className="page-shell">
      <section className="hero-panel">
        <p className="eyebrow">Workspace</p>
        <h1>Welcome back, {session.username}.</h1>
        <p className="hero-copy">
          Your clinical workspace is ready. Use the navigation above to access billing,
          or consult the API documentation to integrate the AI endpoints.
        </p>
        <div className="hero-actions">
          <button className="primary-action" onClick={() => navigate(ROUTES.BILLING)}>
            View billing
          </button>
          <a className="secondary-action" href="/api/schema/swagger-ui/">
            API docs
          </a>
        </div>
      </section>
    </main>
  );
}

// internal helper to avoid import cycle — AppShellContext is provided above
import { useAppShell as useAppShell_inner } from './AppShellContext';

// ---------------------------------------------------------------------------
// Router outlet
// ---------------------------------------------------------------------------

function RouterOutlet({ isAuthenticated }) {
  const { route, navigate } = useRouter();

  // Redirect authenticated users away from auth pages
  useEffect(() => {
    if (isAuthenticated && (route === ROUTES.LOGIN || route === ROUTES.SIGNUP)) {
      navigate(ROUTES.WORKSPACE);
    }
  }, [isAuthenticated, route, navigate]);

  if (route === ROUTES.LOGIN) return <LoginPage />;
  if (route === ROUTES.SIGNUP) return <SignupPage />;
  if (route === ROUTES.BILLING) return <BillingPage />;
  if (route === ROUTES.WORKSPACE) return <WorkspacePage />;
  return <HomePage />;
}

// ---------------------------------------------------------------------------
// Root
// ---------------------------------------------------------------------------

export default function App() {
  const appSession = useAppSession();
  const {
    session,
    credentials,
    setCredentials,
    login,
    logout,
    loading,
    error,
    isAuthenticated,
    setTenantId,
    activeMembership,
  } = appSession;

  const shellValue = {
    session,
    credentials,
    setCredentials,
    login,
    logout,
    loading,
    error,
    isAuthenticated,
    setTenantId,
    activeMembership,
  };

  return (
    <RouterProvider>
      <AppShellProvider value={shellValue}>
        <Topbar session={session} isAuthenticated={isAuthenticated} logout={logout} />
        <RouterOutlet isAuthenticated={isAuthenticated} />
      </AppShellProvider>
    </RouterProvider>
  );
}

