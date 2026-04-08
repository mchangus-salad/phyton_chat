import { useCallback } from 'react';
import { ROUTES, useRouter } from '../../../app/RouterContext';
import { useAppShell } from '../../../app/AppShellContext';
import { useSignup } from '../hooks/useSignup';

export function SignupPage() {
  const { navigate } = useRouter();
  const { login, setCredentials } = useAppShell();

  const handleSuccess = useCallback(
    async (_response) => {
      // Auto-login: credentials were already captured in form; re-use them to
      // obtain a full session token (with tenant membership claims).
      // We pass control to the standard login flow via the form state.
      navigate(ROUTES.LOGIN);
    },
    [navigate],
  );

  const { form, setField, loading, error, fieldErrors, submit } = useSignup({ onSuccess: handleSuccess });

  async function handleSubmit(e) {
    e.preventDefault();
    const response = await submit();
    if (response) {
      // Pre-fill login credentials so the user just clicks "Sign in"
      setCredentials({ username: form.username, password: '' });
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card auth-card--wide">
        <div className="auth-card__header">
          <p className="eyebrow">CliniGraph AI</p>
          <h1>Create your account</h1>
          <p className="auth-card__subtitle">
            Start accessing clinical decision support in minutes.
          </p>
        </div>

        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          <div className="auth-form__row">
            <div className="auth-form__field">
              <label className="auth-form__label" htmlFor="signup-first-name">
                First name
              </label>
              <input
                id="signup-first-name"
                type="text"
                className="auth-form__input"
                value={form.firstName}
                onChange={(e) => setField('firstName', e.target.value)}
                autoComplete="given-name"
              />
            </div>
            <div className="auth-form__field">
              <label className="auth-form__label" htmlFor="signup-last-name">
                Last name
              </label>
              <input
                id="signup-last-name"
                type="text"
                className="auth-form__input"
                value={form.lastName}
                onChange={(e) => setField('lastName', e.target.value)}
                autoComplete="family-name"
              />
            </div>
          </div>

          <div className="auth-form__field">
            <label className="auth-form__label" htmlFor="signup-username">
              Username <span className="auth-form__required">*</span>
            </label>
            <input
              id="signup-username"
              type="text"
              className={`auth-form__input${fieldErrors.username ? ' auth-form__input--error' : ''}`}
              value={form.username}
              onChange={(e) => setField('username', e.target.value)}
              autoComplete="username"
              autoFocus
              required
            />
            {fieldErrors.username && (
              <p className="auth-form__field-error">{fieldErrors.username}</p>
            )}
          </div>

          <div className="auth-form__field">
            <label className="auth-form__label" htmlFor="signup-email">
              Email address <span className="auth-form__required">*</span>
            </label>
            <input
              id="signup-email"
              type="email"
              className={`auth-form__input${fieldErrors.email ? ' auth-form__input--error' : ''}`}
              value={form.email}
              onChange={(e) => setField('email', e.target.value)}
              autoComplete="email"
              required
            />
            {fieldErrors.email && (
              <p className="auth-form__field-error">{fieldErrors.email}</p>
            )}
          </div>

          <div className="auth-form__field">
            <label className="auth-form__label" htmlFor="signup-password">
              Password <span className="auth-form__required">*</span>
            </label>
            <input
              id="signup-password"
              type="password"
              className={`auth-form__input${fieldErrors.password ? ' auth-form__input--error' : ''}`}
              value={form.password}
              onChange={(e) => setField('password', e.target.value)}
              autoComplete="new-password"
              required
            />
            {fieldErrors.password && (
              <p className="auth-form__field-error">{fieldErrors.password}</p>
            )}
          </div>

          <div className="auth-form__field">
            <label className="auth-form__label" htmlFor="signup-confirm-password">
              Confirm password <span className="auth-form__required">*</span>
            </label>
            <input
              id="signup-confirm-password"
              type="password"
              className={`auth-form__input${fieldErrors.confirmPassword ? ' auth-form__input--error' : ''}`}
              value={form.confirmPassword}
              onChange={(e) => setField('confirmPassword', e.target.value)}
              autoComplete="new-password"
              required
            />
            {fieldErrors.confirmPassword && (
              <p className="auth-form__field-error">{fieldErrors.confirmPassword}</p>
            )}
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
            {loading ? 'Creating account…' : 'Create account'}
          </button>
        </form>

        <p className="auth-card__footer">
          Already have an account?{' '}
          <button
            type="button"
            className="auth-card__link"
            onClick={() => navigate(ROUTES.LOGIN)}
          >
            Sign in
          </button>
        </p>
      </div>
    </div>
  );
}
