import { useState } from 'react';
import { useOncologyQuery } from '../hooks/useOncologyQuery';
import { useI18n } from '../../../shared/i18n/I18nProvider';
import { useRuntimeTranslation, useRuntimeTranslationList } from '../../../shared/i18n/useRuntimeTranslation';

export function OncologyQueryPanel() {
  const { t } = useI18n();
  const [authToken, setAuthToken] = useState('');
  const [tenantId, setTenantId] = useState('');
  const [question, setQuestion] = useState('');
  const { status, data, error, errorCode, query } = useOncologyQuery();
  const rawAnswer = data?.answer || data?.message || (data ? JSON.stringify(data) : '');
  const { translatedText, translating, rateLimited: answerRateLimited, retryAfterSeconds: answerRetryAfterSeconds } = useRuntimeTranslation({
    text: rawAnswer,
    authToken,
    tenantId: tenantId || undefined,
  });
  const { translatedTexts: translatedCitations, translating: translatingCitations, rateLimited: citationsRateLimited, retryAfterSeconds: citationsRetryAfterSeconds } = useRuntimeTranslationList({
    texts: Array.isArray(data?.citations) ? data.citations : [],
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
    <section className="oncology-query-panel card">
      <h2>{t('genai.oncologyTitle')}</h2>
      <p className="description">
        {t('genai.oncologyDescription')}
      </p>

      {/* Configuration Section */}
      <div className="form-section">
        <h3>{t('genai.configuration')}</h3>
        <div className="form-group">
          <label htmlFor="oncology-auth-token">{t('genai.authToken')}</label>
          <input
            id="oncology-auth-token"
            type="password"
            value={authToken}
            onChange={(e) => setAuthToken(e.target.value)}
            placeholder={t('genai.jwtPlaceholder')}
            disabled={status === 'loading'}
          />
        </div>

        <div className="form-group">
          <label htmlFor="oncology-tenant-id">{t('genai.tenantIdOptional')}</label>
          <input
            id="oncology-tenant-id"
            type="text"
            value={tenantId}
            onChange={(e) => setTenantId(e.target.value)}
            placeholder={t('genai.tenantPlaceholder')}
            disabled={status === 'loading'}
          />
        </div>
      </div>

      {/* Query Form */}
      <form onSubmit={handleSubmit} className="form-section">
        <div className="form-group">
          <label htmlFor="oncology-question">{t('genai.researchQuestion')}</label>
          <textarea
            id="oncology-question"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder={t('genai.oncologyQuestionPlaceholder')}
            disabled={status === 'loading'}
            rows="4"
          />
        </div>

        <button type="submit" disabled={status === 'loading'} className="primary-action">
          {status === 'loading' ? t('genai.searching') : t('genai.searchOncologyCorpus')}
        </button>
      </form>

      {/* Error Display */}
      {error && (
        <div className={`alert alert-error ${isSubscriptionError ? 'alert-payment-required' : ''}`}>
          <strong>{t('ui.errorTitle')} (HTTP {errorCode}):</strong>
          <p>{error}</p>

          {isSubscriptionError && (
            <div className="alert-actions">
              <a href="/billing" className="action-link">
                {t('genai.upgradeSubscription')}
              </a>
            </div>
          )}

          {isAuthError && (
            <div className="alert-actions">
              <a href="/login" className="action-link">
                {t('ui.logIn')}
              </a>
            </div>
          )}

          {isPermissionError && (
            <p className="alert-subtext">
              {t('genai.oncologyForbiddenHint')}
            </p>
          )}
        </div>
      )}

      {/* Success Display */}
      {status === 'success' && data && (
        <div className="alert alert-success">
          <h4>{t('genai.researchResults')}</h4>
          <div className="response-content">
            <p>{translatedText}</p>
            {translating ? <p className="billing-note">{t('genai.translating')}</p> : null}
            {translationRateLimited ? (
              <p className="billing-note">{t('genai.translationRateLimited', { seconds: translationRetrySeconds })}</p>
            ) : null}

            {data.citations && (
              <div className="citations">
                <h5>{t('genai.researchSources')}</h5>
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
