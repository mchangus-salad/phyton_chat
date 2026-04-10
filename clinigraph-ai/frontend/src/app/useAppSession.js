import { useCallback, useMemo, useState } from 'react';

import { apiPost } from '../shared/api/http';

const STORAGE_KEY = 'clinigraph.session';

const emptySession = {
  accessToken: '',
  refreshToken: '',
  username: '',
  userId: null,
  memberships: [],
  roles: [],
  tenantId: '',
  isStaff: false,
};

function toBase64(value) {
  let normalized = value.replace(/-/g, '+').replace(/_/g, '/');
  while (normalized.length % 4 !== 0) {
    normalized += '=';
  }
  return normalized;
}

function decodeJwtPayload(token) {
  if (!token) return null;
  const parts = token.split('.');
  if (parts.length < 2) return null;

  try {
    const decoded = window.atob(toBase64(parts[1]));
    return JSON.parse(decoded);
  } catch (_error) {
    return null;
  }
}

function sanitizeSession(candidate) {
  if (!candidate || typeof candidate !== 'object') {
    return emptySession;
  }

  return {
    accessToken: candidate.accessToken || '',
    refreshToken: candidate.refreshToken || '',
    username: candidate.username || '',
    userId: candidate.userId ?? null,
    memberships: Array.isArray(candidate.memberships) ? candidate.memberships : [],
    roles: Array.isArray(candidate.roles) ? candidate.roles : [],
    tenantId: candidate.tenantId || '',
    isStaff: Boolean(candidate.isStaff),
  };
}

function readStoredSession() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return emptySession;
    return sanitizeSession(JSON.parse(raw));
  } catch (_error) {
    return emptySession;
  }
}

function isExpired(token) {
  const payload = decodeJwtPayload(token);
  if (!payload?.exp) return false;
  return payload.exp * 1000 <= Date.now();
}

function deriveTenantId(payload, previousTenantId) {
  const memberships = Array.isArray(payload?.tenant_memberships) ? payload.tenant_memberships : [];
  if (previousTenantId && memberships.some((item) => item.tenant_id === previousTenantId)) {
    return previousTenantId;
  }
  return memberships[0]?.tenant_id || previousTenantId || '';
}

export function useAppSession() {
  const initial = sanitizeSession(readStoredSession());
  const [session, setSession] = useState(
    initial.accessToken && !isExpired(initial.accessToken) ? initial : emptySession,
  );
  const [credentials, setCredentials] = useState({ username: initial.username || '', password: '' });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const persistSession = useCallback((nextSession) => {
    const sanitized = sanitizeSession(nextSession);
    setSession(sanitized);
    if (sanitized.accessToken) {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(sanitized));
    } else {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  }, []);

  const login = useCallback(async () => {
    const username = credentials.username.trim();
    const password = credentials.password;

    if (!username || !password) {
      setError('Enter username and password.');
      return false;
    }

    setLoading(true);
    setError('');
    try {
      const response = await apiPost('/auth/token/', { username, password });
      const payload = decodeJwtPayload(response.access);
      const nextSession = {
        accessToken: response.access || '',
        refreshToken: response.refresh || '',
        username,
        userId: payload?.user_id ?? null,
        memberships: Array.isArray(payload?.tenant_memberships) ? payload.tenant_memberships : [],
        roles: Array.isArray(payload?.roles) ? payload.roles : [],
        tenantId: deriveTenantId(payload, session.tenantId),
        isStaff: Boolean(payload?.is_staff_user),
      };

      persistSession(nextSession);
      setCredentials((current) => ({ ...current, username, password: '' }));
      return true;
    } catch (apiError) {
      setError(apiError?.payload?.detail || apiError?.payload?.error || 'Unable to sign in.');
      persistSession(emptySession);
      return false;
    } finally {
      setLoading(false);
    }
  }, [credentials.password, credentials.username, persistSession, session.tenantId]);

  const logout = useCallback(() => {
    persistSession(emptySession);
    setCredentials((current) => ({ ...current, password: '' }));
    setError('');
  }, [persistSession]);

  const setTenantId = useCallback(
    (tenantId) => {
      persistSession({ ...session, tenantId });
    },
    [persistSession, session],
  );

  const activeMembership = useMemo(
    () => session.memberships.find((item) => item.tenant_id === session.tenantId) || null,
    [session.memberships, session.tenantId],
  );

  return {
    session,
    credentials,
    setCredentials,
    login,
    logout,
    setTenantId,
    loading,
    error,
    isAuthenticated: Boolean(session.accessToken),
    isStaff: session.isStaff,
    activeMembership,
  };
}