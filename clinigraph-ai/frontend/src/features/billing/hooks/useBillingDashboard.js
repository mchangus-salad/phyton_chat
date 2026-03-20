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

export function useBillingDashboard() {
  const [plans, setPlans] = useState([]);
  const [selectedPlanCode, setSelectedPlanCode] = useState('');
  const [estimateInput, setEstimateInput] = useState(defaultEstimateInput);
  const [estimateResult, setEstimateResult] = useState(null);
  const [usageSummary, setUsageSummary] = useState(null);
  const [authToken, setAuthToken] = useState('');
  const [tenantId, setTenantId] = useState('');
  const [exportFilters, setExportFilters] = useState(defaultExportFilters);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

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
    } catch (_error) {
      setUsageSummary(null);
      setEstimateResult(null);
      setError('Unable to load protected billing metrics. Verify JWT token and tenant id.');
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
    refreshTenantData,
    exportTenantCsv,
    loading,
    error,
  };
}
