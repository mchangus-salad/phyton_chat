import { useState } from 'react';
import { apiPost, apiPostNdjson } from '../../../shared/api/http';
import { useI18n } from '../../../shared/i18n/I18nProvider';

const initialState = {
  status: 'idle', // idle, loading, success, error
  data: null,
  error: null,
  errorCode: null,
};

export function useAgentQuery() {
  const { t } = useI18n();
  const [state, setState] = useState(initialState);

  async function query(question, authToken, tenantId) {
    setState({ status: 'loading', data: null, error: null, errorCode: null });

    try {
      const headers = {
        Authorization: `Bearer ${authToken}`,
        ...(tenantId && { 'X-Tenant-ID': tenantId }),
      };

      let streamedAnswer = '';
      const response = await apiPostNdjson('/agent/query/stream/', { question }, {
        headers,
        onEvent: (event) => {
          if (event?.event === 'delta') {
            streamedAnswer += event.delta || '';
            setState((prev) => ({
              status: 'loading',
              data: {
                ...(prev.data || {}),
                answer: streamedAnswer,
              },
              error: null,
              errorCode: null,
            }));
          }
        },
      }).catch(async (streamErr) => {
        // Fallback keeps compatibility if stream is not available in a deployment.
        if (streamErr?.status === 404 || streamErr?.status === 405) {
          return apiPost('/agent/query/', { question }, { headers });
        }
        throw streamErr;
      });

      const normalized = response?.event === 'done'
        ? {
            answer: response.answer || streamedAnswer,
            cache_hit: response.cache_hit,
            request_id: response.request_id,
          }
        : response;

      setState({
        status: 'success',
        data: normalized,
        error: null,
        errorCode: null,
      });

      return normalized;
    } catch (err) {
      const errorCode = err.status || 500;
      let errorMessage = t('errors.generic');

      if (errorCode === 401) {
        errorMessage = t('errors.auth');
      } else if (errorCode === 402) {
        errorMessage = t('errors.subscription');
      } else if (errorCode === 403) {
        errorMessage = t('errors.forbidden');
      } else if (errorCode === 429) {
        errorMessage = t('errors.rateLimit');
      } else if (errorCode === 400) {
        errorMessage = err.payload?.detail || t('errors.invalidInput');
      } else if (errorCode >= 500) {
        errorMessage = t('errors.server');
      }

      setState({
        status: 'error',
        data: null,
        error: errorMessage,
        errorCode,
      });

      throw err;
    }
  }

  return { ...state, query };
}
