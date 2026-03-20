import { useEffect, useState } from 'react';

import { apiGet } from '../../../shared/api/http';

const idleState = {
  status: 'idle',
  framework: null,
  requestId: null,
};

export function usePlatformSnapshot() {
  const [health, setHealth] = useState(idleState);

  useEffect(() => {
    let cancelled = false;

    async function loadHealth() {
      setHealth((current) => ({ ...current, status: 'loading' }));
      try {
        const payload = await apiGet('/health/');
        if (cancelled) {
          return;
        }
        setHealth({
          status: payload.status || 'ok',
          framework: payload.framework || 'unknown',
          requestId: payload.request_id || null,
        });
      } catch (_error) {
        if (cancelled) {
          return;
        }
        setHealth({
          status: 'error',
          framework: null,
          requestId: null,
        });
      }
    }

    loadHealth();
    return () => {
      cancelled = true;
    };
  }, []);

  return { health };
}