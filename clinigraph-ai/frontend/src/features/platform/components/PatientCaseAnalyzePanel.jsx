import { useState } from 'react';
import { usePatientCaseAnalyze } from '../hooks/usePatientCaseAnalyze';
import { useI18n } from '../../../shared/i18n/I18nProvider';
import { useRuntimeTranslation, useRuntimeTranslationList } from '../../../shared/i18n/useRuntimeTranslation';

const DOMAINS = [
  { value: 'cardiology', label: 'domainCardiology' },
  { value: 'neurology', label: 'domainNeurology' },
  { value: 'oncology', label: 'domainOncology' },
  { value: 'gastroenterology', label: 'domainGastroenterology' },
  { value: 'pulmonology', label: 'domainPulmonology' },
];

export function PatientCaseAnalyzePanel() {
  const { t } = useI18n();
  const [authToken, setAuthToken] = useState('');
  const [tenantId, setTenantId] = useState('');
  const [inputMode, setInputMode] = useState('text'); // 'text' or 'file'
  const [caseText, setCaseText] = useState('');
  const [caseFile, setCaseFile] = useState(null);
  const [domain, setDomain] = useState('cardiology');
  const [question, setQuestion] = useState('');
  const { status, data, error, errorCode, analyze } = usePatientCaseAnalyze();
  const rawAnswer =
    data?.recommendations || data?.answer || data?.message || (data ? JSON.stringify(data) : '');
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

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      setCaseFile(e.target.files[0]);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!authToken) {
      alert(t('genai.provideAuthToken'));
      return;
    }

    if (inputMode === 'text' && !caseText.trim()) {
      alert(t('genai.providePatientInfo'));
      return;
    }

    if (inputMode === 'file' && !caseFile) {
      alert(t('genai.selectFile'));
      return;
    }

    try {
      const payload = {
        domain,
        question: question || undefined,
      };

      if (inputMode === 'text') {
        payload.text = caseText;
      } else {
        payload.file = caseFile;
      }

      await analyze(payload, authToken, tenantId || undefined);
      setCaseText('');
      setCaseFile(null);
      setQuestion('');
    } catch {
      // Error is handled by hook
    }
  };

  const isSubscriptionError = errorCode === 402;
  const isAuthError = errorCode === 401;
  const isPermissionError = errorCode === 403;

  return (
    <section className="patient-case-analyze-panel card">
      <h2>{t('genai.patientTitle')}</h2>
      <p className="description">
        {t('genai.patientDescription')}
      </p>

      {/* Configuration Section */}
      <div className="form-section">
        <h3>{t('genai.configuration')}</h3>
        <div className="form-group">
          <label htmlFor="patient-auth-token">{t('genai.authToken')}</label>
          <input
            id="patient-auth-token"
            type="password"
            value={authToken}
            onChange={(e) => setAuthToken(e.target.value)}
            placeholder={t('genai.jwtPlaceholder')}
            disabled={status === 'loading'}
          />
        </div>

        <div className="form-group">
          <label htmlFor="patient-tenant-id">{t('genai.tenantIdOptional')}</label>
          <input
            id="patient-tenant-id"
            type="text"
            value={tenantId}
            onChange={(e) => setTenantId(e.target.value)}
            placeholder={t('genai.tenantPlaceholder')}
            disabled={status === 'loading'}
          />
        </div>
      </div>

      {/* Analysis Form */}
      <form onSubmit={handleSubmit} className="form-section">
        <div className="form-group">
          <label htmlFor="patient-domain">{t('genai.clinicalDomain')}</label>
          <select
            id="patient-domain"
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

        {/* Input Mode Toggle */}
        <div className="form-group">
          <label>{t('genai.patientCaseInput')}</label>
          <div className="toggle-group">
            <button
              type="button"
              className={`toggle-btn ${inputMode === 'text' ? 'active' : ''}`}
              onClick={() => setInputMode('text')}
              disabled={status === 'loading'}
            >
              {t('genai.textMode')}
            </button>
            <button
              type="button"
              className={`toggle-btn ${inputMode === 'file' ? 'active' : ''}`}
              onClick={() => setInputMode('file')}
              disabled={status === 'loading'}
            >
              {t('genai.fileMode')}
            </button>
          </div>
        </div>

        {/* Text Input */}
        {inputMode === 'text' && (
          <div className="form-group">
            <label htmlFor="patient-text">{t('genai.patientCaseText')}</label>
            <textarea
              id="patient-text"
              value={caseText}
              onChange={(e) => setCaseText(e.target.value)}
              placeholder={t('genai.patientCaseTextPlaceholder')}
              disabled={status === 'loading'}
              rows="6"
            />
            <p className="field-hint">
              {t('genai.confidentialHint')}
            </p>
          </div>
        )}

        {/* File Upload */}
        {inputMode === 'file' && (
          <div className="form-group">
            <label htmlFor="patient-file">{t('genai.uploadDocument')}</label>
            <input
              id="patient-file"
              type="file"
              accept=".pdf,.txt,.doc,.docx"
              onChange={handleFileChange}
              disabled={status === 'loading'}
            />
            <p className="field-hint">
              {t('genai.acceptedFormats')}
            </p>
            {caseFile && (
              <p className="file-info">
                {t('genai.selectedFile')}: {caseFile.name} ({(caseFile.size / 1024).toFixed(1)} KB)
              </p>
            )}
          </div>
        )}

        {/* Optional Question */}
        <div className="form-group">
          <label htmlFor="patient-question">{t('genai.clinicalQuestionOptional')}</label>
          <textarea
            id="patient-question"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder={t('genai.clinicalQuestionPlaceholder')}
            disabled={status === 'loading'}
            rows="3"
          />
        </div>

        <button type="submit" disabled={status === 'loading'} className="primary-action">
          {status === 'loading' ? t('genai.analyzing') : t('genai.analyzePatientCase')}
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
                {t('genai.checkSubscriptionStatus')}
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
              {t('genai.patientForbiddenHint')}
            </p>
          )}
        </div>
      )}

      {/* Success Display */}
      {status === 'success' && data && (
        <div className="alert alert-success">
          <h4>{t('genai.clinicalRecommendations')}</h4>
          <div className="response-content">
            <p>{translatedText}</p>
            {translating ? <p className="billing-note">{t('genai.translating')}</p> : null}
            {translationRateLimited ? (
              <p className="billing-note">{t('genai.translationRateLimited', { seconds: translationRetrySeconds })}</p>
            ) : null}

            {data.citations && (
              <div className="citations">
                <h5>{t('genai.evidenceBasedReferences')}</h5>
                <ul>
                  {(translatedCitations.length > 0 ? translatedCitations : data.citations).map((citation, idx) => (
                    <li key={idx}>{citation}</li>
                  ))}
                </ul>
                {translatingCitations ? <p className="billing-note">{t('genai.translatingCitations')}</p> : null}
              </div>
            )}

            {data.phi_summary && (
              <div className="phi-notice">
                <h5>{t('genai.phiSummary')}</h5>
                <p>{data.phi_summary}</p>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
