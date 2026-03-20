import { useBillingDashboard } from '../hooks/useBillingDashboard';

function formatMoney(cents, currency) {
  const amount = Number(cents || 0) / 100;
  try {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(amount);
  } catch (_error) {
    return `${amount.toFixed(2)} ${currency}`;
  }
}

export function BillingDashboard() {
  const {
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
  } = useBillingDashboard();

  return (
    <section className="billing-panel">
      <div className="billing-panel__header">
        <p className="eyebrow">Billing cockpit</p>
        <h2>Hybrid billing control plane</h2>
      </div>

      <div className="billing-grid">
        <article className="billing-card">
          <h3>Plan simulator</h3>
          <label>
            Plan
            <select value={selectedPlanCode} onChange={(event) => setSelectedPlanCode(event.target.value)}>
              {plans.map((plan) => (
                <option key={plan.code} value={plan.code}>
                  {plan.name}
                </option>
              ))}
            </select>
          </label>

          <label>
            Active users
            <input
              type="number"
              min="0"
              value={estimateInput.activeUsers}
              onChange={(event) => setEstimateInput((current) => ({ ...current, activeUsers: Number(event.target.value || 0) }))}
            />
          </label>

          <label>
            API requests / month
            <input
              type="number"
              min="0"
              value={estimateInput.apiRequests}
              onChange={(event) => setEstimateInput((current) => ({ ...current, apiRequests: Number(event.target.value || 0) }))}
            />
          </label>

          {simulatedEstimate ? (
            <div className="billing-metrics">
              <p>Base: {formatMoney(simulatedEstimate.platformFeeCents, simulatedEstimate.currency)}</p>
              <p>User overage: {formatMoney(simulatedEstimate.userOverageCents, simulatedEstimate.currency)}</p>
              <p>API overage: {formatMoney(simulatedEstimate.apiOverageCents, simulatedEstimate.currency)}</p>
              <p className="billing-metrics__total">Total: {formatMoney(simulatedEstimate.totalCents, simulatedEstimate.currency)}</p>
            </div>
          ) : null}

          {selectedPlan ? (
            <p className="billing-note">
              Includes {selectedPlan.max_users} users and {selectedPlan.max_monthly_requests} API requests.
            </p>
          ) : null}
        </article>

        <article className="billing-card">
          <h3>Tenant live metrics</h3>
          <label>
            JWT token
            <input
              type="password"
              placeholder="Paste bearer token"
              value={authToken}
              onChange={(event) => setAuthToken(event.target.value)}
            />
          </label>

          <label>
            Tenant id
            <input
              type="text"
              placeholder="Tenant UUID"
              value={tenantId}
              onChange={(event) => setTenantId(event.target.value)}
            />
          </label>

          <div className="billing-export-filters">
            <label>
              Status
              <select
                value={exportFilters.status}
                onChange={(event) => setExportFilters((current) => ({ ...current, status: event.target.value }))}
              >
                <option value="">All</option>
                <option value="draft">Draft</option>
                <option value="finalized">Finalized</option>
                <option value="paid">Paid</option>
                <option value="void">Void</option>
              </select>
            </label>

            <label>
              Currency
              <input
                type="text"
                maxLength="3"
                value={exportFilters.currency}
                onChange={(event) => setExportFilters((current) => ({ ...current, currency: event.target.value.toUpperCase() }))}
              />
            </label>

            <label>
              Generated from
              <input
                type="date"
                value={exportFilters.startDate}
                onChange={(event) => setExportFilters((current) => ({ ...current, startDate: event.target.value }))}
              />
            </label>

            <label>
              Generated to
              <input
                type="date"
                value={exportFilters.endDate}
                onChange={(event) => setExportFilters((current) => ({ ...current, endDate: event.target.value }))}
              />
            </label>

            <label>
              Billed period start
              <input
                type="date"
                value={exportFilters.periodStart}
                onChange={(event) => setExportFilters((current) => ({ ...current, periodStart: event.target.value }))}
              />
            </label>

            <label>
              Billed period end
              <input
                type="date"
                value={exportFilters.periodEnd}
                onChange={(event) => setExportFilters((current) => ({ ...current, periodEnd: event.target.value }))}
              />
            </label>
          </div>

          <button type="button" onClick={refreshTenantData} disabled={loading}>
            {loading ? 'Loading...' : 'Refresh usage and overage'}
          </button>
          <button type="button" className="billing-secondary-button" onClick={exportTenantCsv} disabled={loading}>
            Export CSV
          </button>

          {error ? <p className="billing-error">{error}</p> : null}

          {usageSummary ? (
            <div className="billing-metrics">
              <p>Active users: {usageSummary.active_users}</p>
              <p>API requests: {usageSummary.api_requests}</p>
              <p>Overage users: {usageSummary.overage_users}</p>
              <p>Overage API: {usageSummary.overage_api_requests}</p>
              {usageSummary.latest_invoice ? (
                <p>
                  Latest invoice:{' '}
                  <a
                    href={`/api/v1/billing/invoices/${usageSummary.latest_invoice.invoice_id}/receipt.txt`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    download receipt
                  </a>
                  {' · '}
                  <a
                    href={`/api/v1/billing/invoices/${usageSummary.latest_invoice.invoice_id}/receipt.pdf`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    download PDF
                  </a>
                </p>
              ) : null}
            </div>
          ) : null}

          {estimateResult ? (
            <div className="billing-metrics">
              <p className="billing-metrics__total">
                Current estimate: {formatMoney(estimateResult.total_cents, estimateResult.currency)}
              </p>
            </div>
          ) : null}
        </article>
      </div>
    </section>
  );
}
