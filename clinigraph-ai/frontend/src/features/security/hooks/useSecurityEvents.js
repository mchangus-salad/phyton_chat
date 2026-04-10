import { useCallback, useState } from 'react';
import { apiGet } from '../../../shared/api/http';

export function useSecurityEvents({ authToken, limit = 100 }) {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [loadedAt, setLoadedAt] = useState(null);

  const refresh = useCallback(async () => {
    if (!authToken) {
      setError('Authentication required.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const data = await apiGet(`/security/events/recent/?limit=${limit}`, {
        headers: { Authorization: `Bearer ${authToken}` },
      });
      setEvents(Array.isArray(data) ? data : []);
      setLoadedAt(new Date());
    } catch (err) {
      if (err?.status === 403) {
        setError('Staff access required to view security events.');
      } else {
        setError(err?.payload?.error || 'Failed to load security events.');
      }
    } finally {
      setLoading(false);
    }
  }, [authToken, limit]);

  return { events, loading, error, loadedAt, refresh };
}
