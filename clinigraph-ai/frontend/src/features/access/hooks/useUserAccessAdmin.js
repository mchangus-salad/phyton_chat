import { useState } from 'react';

import { apiGet, apiPatch, apiPost } from '../../../shared/api/http';

const defaultCreateInput = {
  username: '',
  email: '',
  password: '',
  role: 'clinician',
};

export function useUserAccessAdmin() {
  const [authToken, setAuthToken] = useState('');
  const [tenantId, setTenantId] = useState('');
  const [createInput, setCreateInput] = useState(defaultCreateInput);
  const [members, setMembers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  function tenantHeaders() {
    return {
      Authorization: `Bearer ${authToken.trim()}`,
      'X-Tenant-ID': tenantId.trim(),
    };
  }

  async function loadMembers() {
    if (!authToken.trim() || !tenantId.trim()) {
      setError('JWT token and tenant id are required.');
      setSuccess('');
      return;
    }

    setLoading(true);
    setError('');
    setSuccess('');
    try {
      const payload = await apiGet('/tenants/memberships/', { headers: tenantHeaders() });
      setMembers(Array.isArray(payload) ? payload : []);
    } catch (apiError) {
      setError(apiError?.payload?.error || 'Unable to load tenant members.');
      setMembers([]);
    } finally {
      setLoading(false);
    }
  }

  async function createMember() {
    if (!authToken.trim() || !tenantId.trim()) {
      setError('JWT token and tenant id are required.');
      setSuccess('');
      return;
    }

    setLoading(true);
    setError('');
    setSuccess('');
    try {
      const payload = {
        role: createInput.role,
      };
      if (createInput.username.trim()) {
        payload.username = createInput.username.trim();
      }
      if (createInput.email.trim()) {
        payload.email = createInput.email.trim();
      }
      if (createInput.password.trim()) {
        payload.password = createInput.password.trim();
      }

      await apiPost('/tenants/memberships/create/', payload, { headers: tenantHeaders() });
      setCreateInput(defaultCreateInput);
      setSuccess('Member created or updated successfully.');
      await loadMembers();
    } catch (apiError) {
      setError(apiError?.payload?.error || 'Unable to create member.');
    } finally {
      setLoading(false);
    }
  }

  async function updateMember(membershipId, updates) {
    if (!authToken.trim() || !tenantId.trim()) {
      setError('JWT token and tenant id are required.');
      setSuccess('');
      return;
    }

    setLoading(true);
    setError('');
    setSuccess('');
    try {
      await apiPatch(`/tenants/memberships/${membershipId}/`, updates, { headers: tenantHeaders() });
      setSuccess('Membership updated.');
      await loadMembers();
    } catch (apiError) {
      setError(apiError?.payload?.error || 'Unable to update member.');
    } finally {
      setLoading(false);
    }
  }

  return {
    authToken,
    setAuthToken,
    tenantId,
    setTenantId,
    createInput,
    setCreateInput,
    members,
    loading,
    error,
    success,
    loadMembers,
    createMember,
    updateMember,
  };
}
