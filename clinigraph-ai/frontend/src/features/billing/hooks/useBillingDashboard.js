import { useEffect, useMemo, useState } from 'react';

import { apiGet, apiPost } from '../../../shared/api/http';
import { appConfig } from '../../../app/config';

const defaultEstimateInput = {
  activeUsers: 0,
  apiRequests: 0,
};

const defaultExportFilters = {
  status: '',
  currency: 'USD',
  startDate: '',
  endDate: '',
  periodStart: '',
  periodEnd: '',
};

const defaultCheckoutInput = {
  tenantName: '',
  tenantType: 'individual',
};

function formatGraceDate(dateInput) {
  if (!dateInput) {
    return '';
  }
  const date = new Date(dateInput);
  if (Number.isNaN(date.getTime())) {
    return '';
  }
  return date.toLocaleString();
}

function deriveEntitlementState(summary) {
  if (!summary) {
    return {
      status: 'unknown',
      allowed: false,
      label: 'No data',
      tone: 'neutral',
      message: 'Refresh tenant data to load entitlement status.',
    };
  }

  const status = summary.subscription_status || 'unknown';
  const allowed = Boolean(summary.entitlement_allowed);
  const graceEndsAt = formatGraceDate(summary.grace_period_ends_at);

  if (status === 'active') {
    return {
      status,
      allowed,
      label: 'Active',
      tone: 'ok',
      message: 'Service is fully active.',
    };
  }
  if (status === 'trialing') {
    return {
      status,
      allowed,
      label: 'Trialing',
      tone: 'ok',
      message: 'Trial is active and service access is enabled.',
    };
  }
  if (status === 'past_due' && allowed) {
    return {
      status,
      allowed,
      label: 'Grace period',
      tone: 'warn',
      message: graceEndsAt
        ? `Payment failed. Access remains enabled until ${graceEndsAt}.`
        : 'Payment failed. Access remains enabled for a limited grace period.',
    };
  }
  if (status === 'past_due' && !allowed) {
    return {
      status,
      allowed,
      label: 'Grace expired',
      tone: 'critical',
      message: 'Grace period expired. Service should be suspended until payment is recovered.',
    };
  }
  if (status === 'canceled') {
    return {
      status,
      allowed,
      label: 'Canceled',
      tone: 'critical',
      message: 'Subscription canceled. Service access is suspended.',
    };
  }
  if (status === 'incomplete') {
    return {
      status,
      allowed,
      label: 'Incomplete',
      tone: 'warn',
      message: 'Checkout is incomplete. Complete payment to activate service.',
    };
  }
  return {
    status,
    allowed,
    label: status,
    tone: 'neutral',
    message: 'Entitlement state is available but not mapped to a UI hint.',
  };
}

export function useBillingDashboard() {
  const [plans, setPlans] = useState([]);
  const [selectedPlanCode, setSelectedPlanCode] = useState('');
  const [estimateInput, setEstimateInput] = useState(defaultEstimateInput);
  const [estimateResult, setEstimateResult] = useState(null);
  const [usageSummary, setUsageSummary] = useState(null);
  const [authToken, setAuthToken] = useState('');
  const [tenantId, setTenantId] = useState('');
  const [exportFilters, setExportFilters] = useState(defaultExportFilters);
  const [checkoutInput, setCheckoutInput] = useState(defaultCheckoutInput);
  const [checkoutState, setCheckoutState] = useState({ success: false, canceled: false, sessionId: '' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    setCheckoutState({
      success: query.get('success') === 'true',
      canceled: query.get('canceled') === 'true',
      sessionId: query.get('session_id') || '',
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function loadPlans() {
      try {
        const payload = await apiGet('/billing/plans/');
        if (cancelled) {
          return;
        }
        setPlans(payload || []);
        if ((payload || []).length > 0) {
          setSelectedPlanCode((current) => current || payload[0].code);
        }
      } catch (_error) {
        if (!cancelled) {
          setError('Unable to load billing plans.');
        }
      }
    }

    loadPlans();
    return () => {
      cancelled = true;
    };
  }, []);

  const selectedPlan = useMemo(
    () => plans.find((plan) => plan.code === selectedPlanCode) || null,
    [plans, selectedPlanCode],
  );

  const simulatedEstimate = useMemo(() => {
    if (!selectedPlan) {
      return null;
    }
    const includedUsers = Number(selectedPlan.max_users || 0);
    const includedApiRequests = Number(selectedPlan.max_monthly_requests || 0);
    const activeUsers = Number(estimateInput.activeUsers || 0);
    const apiRequests = Number(estimateInput.apiRequests || 0);

    const overageUsers = Math.max(activeUsers - includedUsers, 0);
    const overageApiRequests = Math.max(apiRequests - includedApiRequests, 0);
    const userOverageCents = overageUsers * Number(selectedPlan.seat_price_cents || 0);
    const apiBlocks = Math.ceil(overageApiRequests / 1000);
    const apiOverageCents = apiBlocks * Number(selectedPlan.api_overage_per_1000_cents || 0);
    const platformFeeCents = Number(selectedPlan.price_cents || 0);

    return {
      platformFeeCents,
      overageUsers,
      overageApiRequests,
      userOverageCents,
      apiOverageCents,
      totalCents: platformFeeCents + userOverageCents + apiOverageCents,
      currency: selectedPlan.currency || 'USD',
    };
  }, [selectedPlan, estimateInput]);

  const entitlementState = useMemo(() => deriveEntitlementState(usageSummary), [usageSummary]);

  async function refreshTenantData() {
    if (!authToken.trim() || !tenantId.trim()) {
      setUsageSummary(null);
      return;
    }
    setLoading(true);
    setError('');
    try {
      const summary = await apiGet('/billing/usage/summary/', {
        headers: {
          Authorization: `Bearer ${authToken.trim()}`,
          'X-Tenant-ID': tenantId.trim(),
        },
      });
      setUsageSummary(summary);

      const estimate = await apiPost(
        '/billing/estimate/',
        {},
        {
          headers: {
            Authorization: `Bearer ${authToken.trim()}`,
            'X-Tenant-ID': tenantId.trim(),
          },
        },
      );
      setEstimateResult(estimate);
    } catch (apiError) {
      setEstimateResult(null);
      if (apiError?.status === 402) {
        const detail = apiError?.payload?.detail || 'Service suspended due to billing status.';
        setError(detail);
      } else {
        setUsageSummary(null);
        setError('Unable to load protected billing metrics. Verify JWT token and tenant id.');
      }
    } finally {
      setLoading(false);
    }
  }

  async function exportTenantCsv() {
    if (!authToken.trim() || !tenantId.trim()) {
      setError('JWT token and tenant id are required to export CSV.');
      return;
    }
    if (exportFilters.startDate && exportFilters.endDate && exportFilters.startDate > exportFilters.endDate) {
      setError('Generated date range is invalid.');
      return;
    }
    if (exportFilters.periodStart && exportFilters.periodEnd && exportFilters.periodStart > exportFilters.periodEnd) {
      setError('Billed period range is invalid.');
      return;
    }
    setError('');
    try {
      const params = new URLSearchParams();
      if (exportFilters.status.trim()) {
        params.set('status', exportFilters.status.trim());
      }
      if (exportFilters.currency.trim()) {
        params.set('currency', exportFilters.currency.trim().toUpperCase());
      }
      if (exportFilters.startDate) {
        params.set('start_date', exportFilters.startDate);
      }
      if (exportFilters.endDate) {
        params.set('end_date', exportFilters.endDate);
      }
      if (exportFilters.periodStart) {
        params.set('period_start', exportFilters.periodStart);
      }
      if (exportFilters.periodEnd) {
        params.set('period_end', exportFilters.periodEnd);
      }

      const query = params.toString();
      const response = await fetch(`${appConfig.apiBaseUrl}/billing/invoices/export.csv${query ? `?${query}` : ''}`, {
        method: 'GET',
        headers: {
          Authorization: `Bearer ${authToken.trim()}`,
          'X-Tenant-ID': tenantId.trim(),
        },
      });
      if (!response.ok) {
        throw new Error('CSV export failed');
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `billing-export-${tenantId.trim()}.csv`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(url);
    } catch (_error) {
      setError('Unable to export CSV. Verify JWT token and tenant id.');
    }
  }

  async function startStripeCheckout() {
    if (!authToken.trim()) {
      setError('JWT token is required to create a checkout session.');
      return;
    }
    if (!selectedPlanCode) {
      setError('Select a plan before starting checkout.');
      return;
    }

    setLoading(true);
    setError('');
    try {
      const payload = {
        plan_code: selectedPlanCode,
        tenant_type: checkoutInput.tenantType,
      };
      if (checkoutInput.tenantName.trim()) {
        payload.tenant_name = checkoutInput.tenantName.trim();
      }
      const response = await apiPost('/billing/checkout/session/', payload, {
        headers: {
          Authorization: `Bearer ${authToken.trim()}`,
        },
      });
      if (!response.checkout_url) {
        throw new Error('Checkout URL missing in response');
      }
      window.location.href = response.checkout_url;
    } catch (_error) {
      setError('Unable to start Stripe Checkout. Verify token, plan mapping, and Stripe env config.');
      setLoading(false);
    }
  }

  async function openStripePortal() {
    if (!authToken.trim() || !tenantId.trim()) {
      setError('JWT token and tenant id are required to open billing portal.');
      return;
    }

    setLoading(true);
    setError('');
    try {
      const response = await apiPost(
        '/billing/portal/session/',
        {
          return_url: window.location.origin,
        },
        {
          headers: {
            Authorization: `Bearer ${authToken.trim()}`,
            'X-Tenant-ID': tenantId.trim(),
          },
        },
      );
      if (!response.portal_url) {
        throw new Error('Portal URL missing in response');
      }
      window.location.href = response.portal_url;
    } catch (_error) {
      setError('Unable to open Stripe billing portal. Verify tenant, auth, and Stripe linkage.');
      setLoading(false);
    }
  }

  return {
    plans,
    selectedPlanCode,
    setSelectedPlanCode,
    selectedPlan,
    estimateInput,
    setEstimateInput,
    simulatedEstimate,
    estimateResult,
    usageSummary,
    authToken,
    setAuthToken,
    tenantId,
    setTenantId,
    exportFilters,
    setExportFilters,
    checkoutInput,
    setCheckoutInput,
    checkoutState,
    refreshTenantData,
    exportTenantCsv,
    startStripeCheckout,
    openStripePortal,
    entitlementState,
    loading,
    error,
  };
}
