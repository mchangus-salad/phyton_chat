import { useState } from 'react';
import { useAgentQuery } from '../hooks/useAgentQuery';
import { useI18n } from '../../../shared/i18n/I18nProvider';
import { useRuntimeTranslation, useRuntimeTranslationList } from '../../../shared/i18n/useRuntimeTranslation';
import { useAppShell } from '../../../app/AppShellContext';

function sanitizeDisplayText(text) {
  if (typeof text !== 'string') return '';
  return text
    .replace(/^\s*#{1,6}\s*/gm, '')
    .replace(/\*\*(SUMMARY|EVIDENCE|CLINICAL IMPLICATIONS|UNCERTAINTY\s*&\s*LIMITATIONS|DISCLAIMER)\*\*/gi, '$1');
}

export function AgentQueryPanel({ authToken, tenantId }) {
  const { t } = useI18n();
  const { navigateTo, logout } = useAppShell();
  const [question, setQuestion] = useState('');
  const { status, data, error, errorCode, query } = useAgentQuery();
  const rawAnswer = data?.answer || data?.message || (data ? JSON.stringify(data) : '');
  const translationInput = status === 'success' ? rawAnswer : '';
  const { translatedText, translating, rateLimited: answerRateLimited, retryAfterSeconds: answerRetryAfterSeconds } = useRuntimeTranslation({
    text: translationInput,
    authToken,
    tenantId: tenantId || undefined,
  });
  const displayAnswer = sanitizeDisplayText(status === 'success' ? translatedText : rawAnswer);
  const { translatedTexts: translatedCitations, translating: translatingCitations, rateLimited: citationsRateLimited, retryAfterSeconds: citationsRetryAfterSeconds } = useRuntimeTranslationList({
    texts: status === 'success' && Array.isArray(data?.citations) ? data.citations : [],
    authToken,
    tenantId: tenantId || undefined,
  });
  const translationRateLimited = answerRateLimited || citationsRateLimited;
  const translationRetrySeconds = Math.max(answerRetryAfterSeconds || 0, citationsRetryAfterSeconds || 0);

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!authToken) {
      alert(t('genai.provideAuthToken'));
      return;
    }

    if (!question.trim()) {
      alert(t('genai.provideQuestion'));
      return;
    }

    try {
      await query(question, authToken, tenantId || undefined);
      setQuestion('');
    } catch {
      // Error is handled by hook
    }
  };

  const isSubscriptionError = errorCode === 402;
  const isAuthError = errorCode === 401;
  const isPermissionError = errorCode === 403;

  return (
    <section className="agent-query-panel card">
      <h2>{t('genai.agentTitle')}</h2>
      <p className="description">
        {t('genai.agentDescription')}
      </p>

      <p className="billing-note">{t('genai.authManagedNotice')}</p>

      {/* Query Form */}
      <form onSubmit={handleSubmit} className="form-section">
        <div className="form-group">
          <label htmlFor="question">{t('genai.question')}</label>
          <textarea
            id="question"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder={t('genai.questionPlaceholder')}
            disabled={status === 'loading'}
            rows="4"
          />
        </div>

        <button type="submit" disabled={status === 'loading'} className="primary-action">
          {status === 'loading' ? t('genai.processing') : t('genai.submitQuery')}
        </button>
      </form>

      {/* Error Display */}
      {error && (
        <div className={`alert alert-error ${isSubscriptionError ? 'alert-payment-required' : ''}`}>
          <strong>{t('ui.errorTitle')} (HTTP {errorCode}):</strong>
          <p>{error}</p>

          {isSubscriptionError && (
            <div className="alert-actions">
              <p className="alert-subtext">{t('shell.billingGuidance')}</p>
              <button type="button" className="action-link action-link--button" onClick={() => navigateTo('billing')}>
                {t('shell.openBilling')}
              </button>
            </div>
          )}

          {isAuthError && (
            <div className="alert-actions">
              <p className="alert-subtext">{t('shell.loginGuidance')}</p>
              <button type="button" className="action-link action-link--button" onClick={logout}>
                {t('auth.signOut')}
              </button>
            </div>
          )}

          {isPermissionError && (
            <div className="alert-actions">
              <p className="alert-subtext">{t('ui.contactAdmin')}</p>
              <button type="button" className="action-link action-link--button" onClick={() => navigateTo('users')}>
                {t('nav.users')}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Success Display */}
      {(status === 'success' || (status === 'loading' && rawAnswer)) && data && (
        <div className="alert alert-success">
          <h4>{t('genai.response')}</h4>
          <div className="response-content">
            <div className="response-text">{displayAnswer}</div>
            {status === 'success' && translating ? <p className="billing-note">{t('genai.translating')}</p> : null}
            {translationRateLimited ? (
              <p className="billing-note">{t('genai.translationRateLimited', { seconds: translationRetrySeconds })}</p>
            ) : null}

            {status === 'success' && data.citations && (
              <div className="citations">
                <h5>{t('genai.citations')}</h5>
                <ul>
                  {(translatedCitations.length > 0 ? translatedCitations : data.citations).map((citation, idx) => (
                    <li key={idx}>{citation}</li>
                  ))}
                </ul>
                {translatingCitations ? <p className="billing-note">{t('genai.translatingCitations')}</p> : null}
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
