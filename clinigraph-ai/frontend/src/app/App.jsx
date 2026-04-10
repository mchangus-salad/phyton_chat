import { useMemo, useState } from 'react';
import { UserAccessAdmin } from '../features/access/components/UserAccessAdmin';
import { BillingDashboard } from '../features/billing/components/BillingDashboard';
import { usePlatformSnapshot } from '../features/platform/hooks/usePlatformSnapshot';
import { LanguageSwitcher } from '../shared/ui/LanguageSwitcher';
import { AgentChatWorkspace } from '../features/platform/components/AgentChatWorkspace';
import { OncologyQueryPanel } from '../features/platform/components/OncologyQueryPanel';
import { MedicalQueryPanel } from '../features/platform/components/MedicalQueryPanel';
import { PatientCaseAnalyzePanel } from '../features/platform/components/PatientCaseAnalyzePanel';
import { AgentQueryPanel } from '../features/platform/components/AgentQueryPanel';
import { useI18n } from '../shared/i18n/I18nProvider';
import { useAppSession } from './useAppSession';
import { AppShellProvider } from './AppShellContext';
import { useSignup } from '../features/auth/hooks/useSignup';
import { SecurityDashboard } from '../features/security/components/SecurityDashboard';

function LoginScreen({ credentials, setCredentials, login, loading, error, health, t, onSignUp, successMessage }) {
  return (
    <main className="auth-shell">
      <section className="auth-hero auth-panel">
        <p className="eyebrow">{t('auth.brand')}</p>
        <h1>{t('auth.title')}</h1>
        <p className="auth-copy">{t('auth.subtitle')}</p>
        <div className="auth-health-pill">
          <span className={`status-dot status-dot--${health.status === 'ok' ? 'ok' : health.status === 'loading' ? 'loading' : 'error'}`} />
          <span>{health.status === 'ok' ? t('hero.healthy') : health.status === 'loading' ? t('hero.checking') : t('hero.unavailable')}</span>
        </div>
        <ul className="auth-points">
          <li>{t('auth.pointOne')}</li>
          <li>{t('auth.pointTwo')}</li>
          <li>{t('auth.pointThree')}</li>
        </ul>
      </section>

      <section className="auth-panel auth-form-panel">
        <div className="auth-form-header">
          <h2>{t('auth.signInHeading')}</h2>
          <p>{t('auth.internalTokenNotice')}</p>
        </div>

        {successMessage ? <p className="auth-success-message">{successMessage}</p> : null}

        <label className="auth-field">
          <span>{t('auth.username')}</span>
          <input
            type="text"
            autoComplete="username"
            value={credentials.username}
            onChange={(event) => setCredentials((current) => ({ ...current, username: event.target.value }))}
            placeholder={t('auth.usernamePlaceholder')}
          />
        </label>

        <label className="auth-field">
          <span>{t('auth.password')}</span>
          <input
            type="password"
            autoComplete="current-password"
            value={credentials.password}
            onChange={(event) => setCredentials((current) => ({ ...current, password: event.target.value }))}
            placeholder={t('auth.passwordPlaceholder')}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                login();
              }
            }}
          />
        </label>

        <button type="button" className="primary-action auth-submit" onClick={login} disabled={loading}>
          {loading ? t('auth.signingIn') : t('auth.signIn')}
        </button>
        {error ? <p className="billing-error">{error}</p> : null}
        <p className="auth-switch-hint">
          {t('auth.noAccountYet')}{' '}
          <button type="button" className="auth-link" onClick={onSignUp}>
            {t('auth.createAccount')}
          </button>
        </p>
      </section>
    </main>
  );
}

function SignupScreen({ onSignedUp, onBackToLogin, t }) {
  const { form, setField, loading, error, fieldErrors, submit } = useSignup({
    onSuccess: (data) => onSignedUp(data.username),
  });

  return (
    <main className="auth-shell">
      <section className="auth-hero auth-panel">
        <p className="eyebrow">{t('auth.brand')}</p>
        <h1>{t('auth.title')}</h1>
        <p className="auth-copy">{t('auth.createAccountSubtitle')}</p>
        <ul className="auth-points">
          <li>{t('auth.pointOne')}</li>
          <li>{t('auth.pointTwo')}</li>
          <li>{t('auth.pointThree')}</li>
        </ul>
      </section>

      <section className="auth-panel auth-form-panel">
        <div className="auth-form-header">
          <h2>{t('auth.createAccountHeading')}</h2>
        </div>

        <div className="auth-row">
          <label className="auth-field">
            <span>{t('auth.firstName')}</span>
            <input
              type="text"
              value={form.first_name}
              onChange={(e) => setField('first_name', e.target.value)}
              placeholder={t('auth.firstNamePlaceholder')}
            />
          </label>
          <label className="auth-field">
            <span>{t('auth.lastName')}</span>
            <input
              type="text"
              value={form.last_name}
              onChange={(e) => setField('last_name', e.target.value)}
              placeholder={t('auth.lastNamePlaceholder')}
            />
          </label>
        </div>

        <label className="auth-field">
          <span>{t('auth.username')} <span className="auth-required">*</span></span>
          <input
            type="text"
            autoComplete="username"
            value={form.username}
            onChange={(e) => setField('username', e.target.value)}
            placeholder={t('auth.usernamePlaceholder')}
            className={fieldErrors.username ? 'auth-input--error' : ''}
          />
          {fieldErrors.username && <small className="auth-field-error">{fieldErrors.username}</small>}
        </label>

        <label className="auth-field">
          <span>{t('auth.email')} <span className="auth-required">*</span></span>
          <input
            type="email"
            autoComplete="email"
            value={form.email}
            onChange={(e) => setField('email', e.target.value)}
            placeholder={t('auth.emailPlaceholder')}
            className={fieldErrors.email ? 'auth-input--error' : ''}
          />
          {fieldErrors.email && <small className="auth-field-error">{fieldErrors.email}</small>}
        </label>

        <label className="auth-field">
          <span>{t('auth.password')} <span className="auth-required">*</span></span>
          <input
            type="password"
            autoComplete="new-password"
            value={form.password}
            onChange={(e) => setField('password', e.target.value)}
            placeholder={t('auth.passwordPlaceholder')}
            className={fieldErrors.password ? 'auth-input--error' : ''}
          />
          {fieldErrors.password && <small className="auth-field-error">{fieldErrors.password}</small>}
        </label>

        <label className="auth-field">
          <span>{t('auth.confirmPassword')} <span className="auth-required">*</span></span>
          <input
            type="password"
            autoComplete="new-password"
            value={form.confirmPassword}
            onChange={(e) => setField('confirmPassword', e.target.value)}
            placeholder={t('auth.confirmPasswordPlaceholder')}
            className={fieldErrors.confirmPassword ? 'auth-input--error' : ''}
          />
          {fieldErrors.confirmPassword && <small className="auth-field-error">{fieldErrors.confirmPassword}</small>}
        </label>

        <button type="button" className="primary-action auth-submit" onClick={submit} disabled={loading}>
          {loading ? t('auth.creating') : t('auth.createAccount')}
        </button>
        {error ? <p className="billing-error">{error}</p> : null}
        <p className="auth-switch-hint">
          {t('auth.alreadyHaveAccount')}{' '}
          <button type="button" className="auth-link" onClick={onBackToLogin}>
            {t('auth.backToSignIn')}
          </button>
        </p>
      </section>
    </main>
  );
}

function OverviewPage({ health, activeMembership, session, setActiveView, t }) {
  const spotlightCards = [
    {
      id: 'workspace',
      title: t('shell.spotlightWorkspaceTitle'),
      copy: t('shell.spotlightWorkspaceCopy'),
    },
    {
      id: 'research',
      title: t('shell.spotlightResearchTitle'),
      copy: t('shell.spotlightResearchCopy'),
    },
    {
      id: 'patient',
      title: t('shell.spotlightPatientTitle'),
      copy: t('shell.spotlightPatientCopy'),
    },
    {
      id: 'billing',
      title: t('shell.spotlightBillingTitle'),
      copy: t('shell.spotlightBillingCopy'),
    },
  ];

  return (
    <div className="overview-layout">
      <section className="overview-hero panel-surface">
        <p className="eyebrow">{t('shell.commandCenter')}</p>
        <h2>{t('shell.overviewTitle')}</h2>
        <p className="overview-copy">{t('shell.overviewDescription')}</p>
        <div className="overview-actions">
          <button type="button" className="primary-action" onClick={() => setActiveView('workspace')}>
            {t('shell.openWorkspace')}
          </button>
          <button type="button" className="secondary-action" onClick={() => setActiveView('billing')}>
            {t('shell.openBilling')}
          </button>
        </div>
      </section>

      <section className="overview-strip">
        <article className="overview-strip__card panel-surface">
          <p className="eyebrow">{t('shell.healthStatusLabel')}</p>
          <strong>{health.status === 'ok' ? t('hero.healthy') : health.status === 'loading' ? t('hero.checking') : t('hero.unavailable')}</strong>
          <span>{health.framework || t('ui.unknown')}</span>
        </article>
        <article className="overview-strip__card panel-surface">
          <p className="eyebrow">{t('shell.membershipCountLabel')}</p>
          <strong>{session.memberships.length}</strong>
          <span>{t('shell.membershipCountCopy')}</span>
        </article>
        <article className="overview-strip__card panel-surface">
          <p className="eyebrow">{t('shell.roleCountLabel')}</p>
          <strong>{session.roles.length || 0}</strong>
          <span>{t('shell.roleCountCopy')}</span>
        </article>
        <article className="overview-strip__card panel-surface">
          <p className="eyebrow">{t('shell.sessionStateLabel')}</p>
          <strong>{t('shell.sessionStateValue')}</strong>
          <span>{session.username}</span>
        </article>
      </section>

      <section className="overview-spotlights">
        <div className="overview-section-heading">
          <div>
            <p className="eyebrow">{t('shell.quickActions')}</p>
            <h3>{t('shell.quickActionsTitle')}</h3>
          </div>
          <p>{t('shell.quickActionsDescription')}</p>
        </div>
        <div className="overview-spotlights__grid">
          {spotlightCards.map((card) => (
            <article key={card.id} className="overview-spotlight-card panel-surface">
              <h4>{card.title}</h4>
              <p>{card.copy}</p>
              <button type="button" className="secondary-action" onClick={() => setActiveView(card.id)}>
                {t('shell.openSection')}
              </button>
            </article>
          ))}
        </div>
      </section>

      <section className="overview-grid">
        <article className="overview-card panel-surface">
          <p className="eyebrow">{t('shell.currentTenant')}</p>
          <h3>{activeMembership?.tenant_name || t('shell.noTenantSelected')}</h3>
          <p>{activeMembership?.role || t('shell.noTenantHint')}</p>
        </article>
        <article className="overview-card panel-surface">
          <p className="eyebrow">{t('shell.platformHealth')}</p>
          <h3>{health.status === 'ok' ? t('hero.healthy') : health.status === 'loading' ? t('hero.checking') : t('hero.unavailable')}</h3>
          <p>{health.framework || t('ui.unknown')}</p>
        </article>
        <article className="overview-card panel-surface">
          <p className="eyebrow">{t('shell.accessRoles')}</p>
          <h3>{session.roles?.join(', ') || t('ui.na')}</h3>
          <p>{t('shell.sessionManaged')}</p>
        </article>
      </section>
    </div>
  );
}

export default function App() {
  const platformSnapshot = usePlatformSnapshot();
  const { t } = useI18n();
  const { session, credentials, setCredentials, login, logout, setTenantId, loading, error, isAuthenticated, isStaff, activeMembership } = useAppSession();
  const [activeView, setActiveView] = useState('overview');
  const [authView, setAuthView] = useState('login');
  const [signupSuccessMessage, setSignupSuccessMessage] = useState('');

  const views = [
    { id: 'overview', label: t('nav.overview'), title: t('shell.overviewTitle'), description: t('shell.overviewDescription') },
    { id: 'workspace', label: t('nav.workspace'), title: t('shell.workspaceTitle'), description: t('shell.workspaceDescription') },
    { id: 'research', label: t('nav.research'), title: t('shell.researchTitle'), description: t('shell.researchDescription') },
    { id: 'patient', label: t('nav.patientCases'), title: t('shell.patientTitle'), description: t('shell.patientDescription') },
    { id: 'users', label: t('nav.users'), title: t('shell.usersTitle'), description: t('shell.usersDescription') },
    { id: 'billing', label: t('nav.billing'), title: t('shell.billingTitle'), description: t('shell.billingDescription') },
    ...(isStaff ? [{ id: 'security', label: t('nav.security'), title: t('shell.securityTitle'), description: t('shell.securityDescription') }] : []),
  ];

  const activeMeta = views.find((item) => item.id === activeView) || views[0];
  const shellValue = useMemo(
    () => ({
      activeView,
      navigateTo: setActiveView,
      logout,
    }),
    [activeView, logout],
  );

  if (!isAuthenticated) {
    if (authView === 'signup') {
      return (
        <SignupScreen
          onSignedUp={(username) => {
            setCredentials((c) => ({ ...c, username }));
            setSignupSuccessMessage(t('auth.registerSuccess'));
            setAuthView('login');
          }}
          onBackToLogin={() => setAuthView('login')}
          t={t}
        />
      );
    }
    return (
      <LoginScreen
        credentials={credentials}
        setCredentials={setCredentials}
        login={login}
        loading={loading}
        error={error}
        health={platformSnapshot.health}
        t={t}
        onSignUp={() => { setSignupSuccessMessage(''); setAuthView('signup'); }}
        successMessage={signupSuccessMessage}
      />
    );
  }

  function renderActiveView() {
    switch (activeView) {
      case 'workspace':
        return (
          <div className="module-stack">
            <AgentChatWorkspace authToken={session.accessToken} tenantId={session.tenantId} />
            <AgentQueryPanel authToken={session.accessToken} tenantId={session.tenantId} />
          </div>
        );
      case 'research':
        return (
          <div className="module-grid module-grid--dual">
            <OncologyQueryPanel authToken={session.accessToken} tenantId={session.tenantId} />
            <MedicalQueryPanel authToken={session.accessToken} tenantId={session.tenantId} />
          </div>
        );
      case 'patient':
        return <PatientCaseAnalyzePanel authToken={session.accessToken} tenantId={session.tenantId} />;
      case 'users':
        return <UserAccessAdmin authToken={session.accessToken} tenantId={session.tenantId} />;
      case 'billing':
        return <BillingDashboard authToken={session.accessToken} tenantId={session.tenantId} />;
      case 'security':
        return <SecurityDashboard authToken={session.accessToken} isStaff={isStaff} />;
      case 'overview':
      default:
        return (
          <OverviewPage
            health={platformSnapshot.health}
            activeMembership={activeMembership}
            session={session}
            setActiveView={setActiveView}
            t={t}
          />
        );
    }
  }

  return (
    <AppShellProvider value={shellValue}>
      <main className="workspace-shell">
        <aside className="workspace-sidebar panel-surface">
        <div className="workspace-brand">
          <p className="eyebrow">{t('auth.brand')}</p>
          <h1>{t('shell.productName')}</h1>
          <p>{t('shell.sidebarSubtitle')}</p>
        </div>

        <nav className="workspace-nav" aria-label={t('shell.primaryNavigation')}>
          {views.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`workspace-nav__item ${item.id === activeView ? 'workspace-nav__item--active' : ''}`}
              onClick={() => setActiveView(item.id)}
            >
              <span>{item.label}</span>
              <small>{item.description}</small>
            </button>
          ))}
        </nav>

        <div className="workspace-session-card">
          <p className="eyebrow">{t('shell.session')}</p>
          <strong>{session.username}</strong>
          <span>{activeMembership?.tenant_name || session.tenantId || t('shell.noTenantSelected')}</span>
          <button type="button" className="secondary-action workspace-logout" onClick={logout}>
            {t('auth.signOut')}
          </button>
        </div>
        </aside>

        <section className="workspace-main">
          <header className="workspace-topbar panel-surface">
          <div>
            <p className="eyebrow">{t('shell.activeSection')}</p>
            <h2>{activeMeta.title}</h2>
            <p>{activeMeta.description}</p>
          </div>

            <div className="workspace-topbar__controls">
            <label className="tenant-switcher">
              <span>{t('shell.currentTenant')}</span>
              {session.memberships.length > 0 ? (
                <select value={session.tenantId} onChange={(event) => setTenantId(event.target.value)}>
                  {session.memberships.map((membership) => (
                    <option key={membership.tenant_id} value={membership.tenant_id}>
                      {membership.tenant_name} · {membership.role}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  type="text"
                  value={session.tenantId}
                  onChange={(event) => setTenantId(event.target.value)}
                  placeholder={t('shell.tenantPlaceholder')}
                />
              )}
            </label>
            <LanguageSwitcher />
            </div>
          </header>

          <div className="workspace-view">{renderActiveView()}</div>
        </section>
      </main>
    </AppShellProvider>
  );
}