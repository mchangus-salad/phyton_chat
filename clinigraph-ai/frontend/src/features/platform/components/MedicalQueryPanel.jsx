import { useState } from 'react';
import { useMedicalQuery } from '../hooks/useMedicalQuery';
import { useI18n } from '../../../shared/i18n/I18nProvider';
import { useRuntimeTranslation, useRuntimeTranslationList } from '../../../shared/i18n/useRuntimeTranslation';

const DOMAINS = [
  { value: 'cardiology', label: 'domainCardiology' },
  { value: 'neurology', label: 'domainNeurology' },
  { value: 'oncology', label: 'domainOncology' },
  { value: 'gastroenterology', label: 'domainGastroenterology' },
  { value: 'pulmonology', label: 'domainPulmonology' },
];

export function MedicalQueryPanel() {
  const { t } = useI18n();
  const [authToken, setAuthToken] = useState('');
  const [tenantId, setTenantId] = useState('');
  const [question, setQuestion] = useState('');
  const [domain, setDomain] = useState('cardiology');
  const { status, data, error, errorCode, query } = useMedicalQuery();
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
      await query(question, domain, authToken, tenantId || undefined);
      setQuestion('');
    } catch {
      // Error is handled by hook
    }
  };

  const isSubscriptionError = errorCode === 402;
  const isAuthError = errorCode === 401;
  const isPermissionError = errorCode === 403;

  return (
    <section className="medical-query-panel card">
      <h2>{t('genai.medicalTitle')}</h2>
      <p className="description">
        {t('genai.medicalDescription')}
      </p>

      {/* Configuration Section */}
      <div className="form-section">
        <h3>{t('genai.configuration')}</h3>
        <div className="form-group">
          <label htmlFor="medical-auth-token">{t('genai.authToken')}</label>
          <input
            id="medical-auth-token"
            type="password"
            value={authToken}
            onChange={(e) => setAuthToken(e.target.value)}
            placeholder={t('genai.jwtPlaceholder')}
            disabled={status === 'loading'}
          />
        </div>

        <div className="form-group">
          <label htmlFor="medical-tenant-id">{t('genai.tenantIdOptional')}</label>
          <input
            id="medical-tenant-id"
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
          <label htmlFor="medical-domain">{t('genai.clinicalDomain')}</label>
          <select
            id="medical-domain"
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            disabled={status === 'loading'}
          >
            {DOMAINS.map((domainOption) => (
              <option key={domainOption.value} value={domainOption.value}>
                {t(`genai.${domainOption.label}`)}
              </option>
            ))}
          </select>
        </div>

        <div className="form-group">
          <label htmlFor="medical-question">{t('genai.medicalQuestion')}</label>
          <textarea
            id="medical-question"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder={t('genai.medicalQuestionPlaceholder')}
            disabled={status === 'loading'}
            rows="4"
          />
        </div>

        <button type="submit" disabled={status === 'loading'} className="primary-action">
          {status === 'loading' ? t('genai.searching') : t('genai.queryMedicalKnowledge')}
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
                {t('genai.viewSubscriptionOptions')}
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
              {t('genai.medicalForbiddenHint')}
            </p>
          )}
        </div>
      )}

      {/* Success Display */}
      {status === 'success' && data && (
        <div className="alert alert-success">
          <h4>{t('genai.medicalKnowledgeResponse')}</h4>
          <div className="response-content">
            <p>{translatedText}</p>
            {translating ? <p className="billing-note">{t('genai.translating')}</p> : null}
            {translationRateLimited ? (
              <p className="billing-note">{t('genai.translationRateLimited', { seconds: translationRetrySeconds })}</p>
            ) : null}

            {data.citations && (
              <div className="citations">
                <h5>{t('genai.evidenceSources')}</h5>
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
