import { useAppShell } from '../../../app/AppShellContext';
import { ROUTES, useRouter } from '../../../app/RouterContext';
import { BillingDashboard } from './BillingDashboard';

export function BillingPage() {
  const { session, isAuthenticated } = useAppShell();
  const { navigate } = useRouter();

  if (!isAuthenticated) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <div className="auth-card__header">
            <p className="eyebrow">CliniGraph AI</p>
            <h1>Sign in to access billing</h1>
          </div>
          <div className="auth-form">
            <button
              type="button"
              className="auth-form__submit"
              onClick={() => navigate(ROUTES.LOGIN)}
            >
              Go to sign in
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="page-shell">
      <BillingDashboard
        authToken={session.accessToken}
        tenantId={session.tenantId}
      />
    </div>
  );
}
