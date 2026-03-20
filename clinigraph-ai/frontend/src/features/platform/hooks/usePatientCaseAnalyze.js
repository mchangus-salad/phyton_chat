import { useState } from 'react';
import { apiPostFormData } from '../../../shared/api/http';
import { useI18n } from '../../../shared/i18n/I18nProvider';

const initialState = {
  status: 'idle',
  data: null,
  error: null,
  errorCode: null,
};

export function usePatientCaseAnalyze() {
  const { t } = useI18n();
  const [state, setState] = useState(initialState);

  async function analyze(payload, authToken, tenantId) {
    setState({ status: 'loading', data: null, error: null, errorCode: null });

    try {
      const formData = new FormData();

      // Add text or file
      if (payload.text) {
        formData.append('text', payload.text);
      }
      if (payload.file) {
        formData.append('document', payload.file);
      }

      // Add domain and question
      if (payload.domain) {
        formData.append('domain', payload.domain);
      }
      if (payload.question) {
        formData.append('question', payload.question);
      }

      const response = await apiPostFormData(
        '/agent/patient/analyze/',
        formData,
        {
          headers: {
            Authorization: `Bearer ${authToken}`,
            ...(tenantId && { 'X-Tenant-ID': tenantId }),
          },
        }
      );

      setState({
        status: 'success',
        data: response,
        error: null,
        errorCode: null,
      });

      return response;
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
        errorMessage =
          err.payload?.detail ||
          t('errors.invalidInputFile');
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

  return { ...state, analyze };
}
