import { useAppShell } from '../../../app/AppShellContext';
import { ROUTES } from '../../../app/RouterContext';
import { useRouter } from '../../../app/RouterContext';

export function LoginPage() {
  const { credentials, setCredentials, login, loading, error } = useAppShell();
  const { navigate } = useRouter();

  async function handleSubmit(e) {
    e.preventDefault();
    const success = await login();
    if (success) {
      navigate(ROUTES.WORKSPACE);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-card__header">
          <p className="eyebrow">CliniGraph AI</p>
          <h1>Sign in to your workspace</h1>
          <p className="auth-card__subtitle">
            Access clinical decision support and your team workspace.
          </p>
        </div>

        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          <div className="auth-form__field">
            <label className="auth-form__label" htmlFor="login-username">
              Username
            </label>
            <input
              id="login-username"
              type="text"
              className="auth-form__input"
              value={credentials.username}
              onChange={(e) => setCredentials((c) => ({ ...c, username: e.target.value }))}
              autoComplete="username"
              autoFocus
              required
            />
          </div>

          <div className="auth-form__field">
            <label className="auth-form__label" htmlFor="login-password">
              Password
            </label>
            <input
              id="login-password"
              type="password"
              className="auth-form__input"
              value={credentials.password}
              onChange={(e) => setCredentials((c) => ({ ...c, password: e.target.value }))}
              autoComplete="current-password"
              required
            />
          </div>

          {error && (
            <p className="auth-form__error" role="alert">
              {error}
            </p>
          )}

          <button
            type="submit"
            className="auth-form__submit"
            disabled={loading}
          >
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <p className="auth-card__footer">
          Don&rsquo;t have an account?{' '}
          <button
            type="button"
            className="auth-card__link"
            onClick={() => navigate(ROUTES.SIGNUP)}
          >
            Create account
          </button>
        </p>
      </div>
    </div>
  );
}
