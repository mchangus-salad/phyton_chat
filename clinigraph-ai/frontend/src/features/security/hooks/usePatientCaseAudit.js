import { useCallback, useState } from 'react';
import { apiGet } from '../../../shared/api/http';

export function usePatientCaseAudit({ authToken, days = 30, limit = 50 }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const refresh = useCallback(async () => {
    if (!authToken) {
      setError('Authentication required.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const result = await apiGet(
        `/audit/patient-cases/?days=${days}&limit=${limit}`,
        { headers: { Authorization: `Bearer ${authToken}` } },
      );
      setData(result);
    } catch (err) {
      if (err?.status === 403) {
        setError('Staff access required to view patient-case audit log.');
      } else {
        setError(err?.payload?.error || 'Failed to load audit data.');
      }
    } finally {
      setLoading(false);
    }
  }, [authToken, days, limit]);

  return { data, loading, error, refresh };
}
