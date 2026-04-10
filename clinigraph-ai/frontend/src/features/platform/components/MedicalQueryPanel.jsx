import { useState } from 'react';
import { useMedicalQuery } from '../hooks/useMedicalQuery';
import { useI18n } from '../../../shared/i18n/I18nProvider';
import { useRuntimeTranslation, useRuntimeTranslationList } from '../../../shared/i18n/useRuntimeTranslation';
import { useAppShell } from '../../../app/AppShellContext';

function sanitizeDisplayText(text) {
  if (typeof text !== 'string') return '';
  return text
    .replace(/^\s*#{1,6}\s*/gm, '')
    .replace(/\*\*(SUMMARY|EVIDENCE|CLINICAL IMPLICATIONS|UNCERTAINTY\s*&\s*LIMITATIONS|DISCLAIMER)\*\*/gi, '$1');
}

const DOMAINS = [
  { value: 'general',                  label: 'domainGeneral' },
  { value: 'cardiology',               label: 'domainCardiology' },
  { value: 'dermatology',              label: 'domainDermatology' },
  { value: 'emergency-medicine',       label: 'domainEmergencyMedicine' },
  { value: 'endocrinology',            label: 'domainEndocrinology' },
  { value: 'gastroenterology',         label: 'domainGastroenterology' },
  { value: 'geriatrics',               label: 'domainGeriatrics' },
  { value: 'hematology',               label: 'domainHematology' },
  { value: 'infectious-diseases',      label: 'domainInfectiousDiseases' },
  { value: 'nephrology',               label: 'domainNephrology' },
  { value: 'neurology',                label: 'domainNeurology' },
  { value: 'obstetrics-gynecology',    label: 'domainObstetricsGynecology' },
  { value: 'oncology',                 label: 'domainOncology' },
  { value: 'ophthalmology',            label: 'domainOphthalmology' },
  { value: 'orthopedics',              label: 'domainOrthopedics' },
  { value: 'pediatrics',               label: 'domainPediatrics' },
  { value: 'psychiatry',               label: 'domainPsychiatry' },
  { value: 'pulmonology',              label: 'domainPulmonology' },
  { value: 'rheumatology',             label: 'domainRheumatology' },
  { value: 'urology',                  label: 'domainUrology' },
];

export function MedicalQueryPanel({ authToken, tenantId }) {
  const { t } = useI18n();
  const { navigateTo, logout } = useAppShell();
  const [question, setQuestion] = useState('');
  const [domain, setDomain] = useState('general');
  const { status, data, error, errorCode, query } = useMedicalQuery();
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

      <p className="billing-note">{t('genai.authManagedNotice')}</p>

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
              <p className="alert-subtext">{t('genai.medicalForbiddenHint')}</p>
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
          <h4>{t('genai.medicalKnowledgeResponse')}</h4>
          <div className="response-content">
            <div className="response-text">{displayAnswer}</div>
            {status === 'success' && translating ? <p className="billing-note">{t('genai.translating')}</p> : null}
            {translationRateLimited ? (
              <p className="billing-note">{t('genai.translationRateLimited', { seconds: translationRetrySeconds })}</p>
            ) : null}

            {status === 'success' && data.citations && (
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
