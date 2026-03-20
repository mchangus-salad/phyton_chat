import { useBillingDashboard } from '../hooks/useBillingDashboard';
import { useI18n } from '../../../shared/i18n/I18nProvider';

function formatMoney(cents, currency, locale) {
  const amount = Number(cents || 0) / 100;
  try {
    return new Intl.NumberFormat(locale === 'es' ? 'es-ES' : 'en-US', { style: 'currency', currency }).format(amount);
  } catch (_error) {
    return `${amount.toFixed(2)} ${currency}`;
  }
}

function entitlementClassName(tone) {
  if (tone === 'ok') {
    return 'billing-entitlement billing-entitlement--ok';
  }
  if (tone === 'warn') {
    return 'billing-entitlement billing-entitlement--warn';
  }
  if (tone === 'critical') {
    return 'billing-entitlement billing-entitlement--critical';
  }
  return 'billing-entitlement';
}

export function BillingDashboard() {
  const { t, locale } = useI18n();

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
  } = useBillingDashboard();

  return (
    <section className="billing-panel">
      <div className="billing-panel__header">
        <p className="eyebrow">{t('billing.eyebrow')}</p>
        <h2>{t('billing.title')}</h2>
      </div>

      <div className="billing-grid">
        <article className="billing-card">
          <h3>{t('billing.planSimulator')}</h3>
          <label>
            {t('billing.plan')}
            <select value={selectedPlanCode} onChange={(event) => setSelectedPlanCode(event.target.value)}>
              {plans.map((plan) => (
                <option key={plan.code} value={plan.code}>
                  {plan.name}
                </option>
              ))}
            </select>
          </label>

          <label>
            {t('billing.activeUsers')}
            <input
              type="number"
              min="0"
              value={estimateInput.activeUsers}
              onChange={(event) => setEstimateInput((current) => ({ ...current, activeUsers: Number(event.target.value || 0) }))}
            />
          </label>

          <label>
            {t('billing.apiRequestsPerMonth')}
            <input
              type="number"
              min="0"
              value={estimateInput.apiRequests}
              onChange={(event) => setEstimateInput((current) => ({ ...current, apiRequests: Number(event.target.value || 0) }))}
            />
          </label>

          {simulatedEstimate ? (
            <div className="billing-metrics">
              <p>{t('billing.base')}: {formatMoney(simulatedEstimate.platformFeeCents, simulatedEstimate.currency, locale)}</p>
              <p>{t('billing.userOverage')}: {formatMoney(simulatedEstimate.userOverageCents, simulatedEstimate.currency, locale)}</p>
              <p>{t('billing.apiOverage')}: {formatMoney(simulatedEstimate.apiOverageCents, simulatedEstimate.currency, locale)}</p>
              <p className="billing-metrics__total">{t('billing.total')}: {formatMoney(simulatedEstimate.totalCents, simulatedEstimate.currency, locale)}</p>
            </div>
          ) : null}

          {selectedPlan ? (
            <p className="billing-note">
              {t('billing.includes', {
                users: selectedPlan.max_users,
                requests: selectedPlan.max_monthly_requests,
              })}
            </p>
          ) : null}
        </article>

        <article className="billing-card">
          <h3>{t('billing.tenantLiveMetrics')}</h3>

          <div className={entitlementClassName(entitlementState.tone)}>
            <p className="billing-entitlement__label">{t('billing.entitlementStatus')}: {entitlementState.label}</p>
            <p className="billing-entitlement__message">{entitlementState.message}</p>
            {!entitlementState.allowed ? (
              <button type="button" className="billing-secondary-button" onClick={openStripePortal} disabled={loading || !authToken || !tenantId}>
                {t('billing.resolveInPortal')}
              </button>
            ) : null}
          </div>

          <label>
            {t('billing.jwtToken')}
            <input
              type="password"
              placeholder={t('billing.pasteBearer')}
              value={authToken}
              onChange={(event) => setAuthToken(event.target.value)}
            />
          </label>

          <label>
            {t('billing.tenantId')}
            <input
              type="text"
              placeholder={t('billing.tenantUuid')}
              value={tenantId}
              onChange={(event) => setTenantId(event.target.value)}
            />
          </label>

          <label>
            {t('billing.checkoutTenantName')}
            <input
              type="text"
              placeholder={t('billing.orgDisplayName')}
              value={checkoutInput.tenantName}
              onChange={(event) => setCheckoutInput((current) => ({ ...current, tenantName: event.target.value }))}
            />
          </label>

          <label>
            {t('billing.checkoutTenantType')}
            <select
              value={checkoutInput.tenantType}
              onChange={(event) => setCheckoutInput((current) => ({ ...current, tenantType: event.target.value }))}
            >
              <option value="individual">{t('billing.typeIndividual')}</option>
              <option value="clinic">{t('billing.typeClinic')}</option>
              <option value="hospital">{t('billing.typeHospital')}</option>
              <option value="institution">{t('billing.typeInstitution')}</option>
            </select>
          </label>

          <div className="billing-export-filters">
            <label>
              {t('billing.status')}
              <select
                value={exportFilters.status}
                onChange={(event) => setExportFilters((current) => ({ ...current, status: event.target.value }))}
              >
                <option value="">{t('billing.statusAll')}</option>
                <option value="draft">{t('billing.statusDraft')}</option>
                <option value="finalized">{t('billing.statusFinalized')}</option>
                <option value="paid">{t('billing.statusPaid')}</option>
                <option value="void">{t('billing.statusVoid')}</option>
              </select>
            </label>

            <label>
              {t('billing.currency')}
              <input
                type="text"
                maxLength="3"
                value={exportFilters.currency}
                onChange={(event) => setExportFilters((current) => ({ ...current, currency: event.target.value.toUpperCase() }))}
              />
            </label>

            <label>
              {t('billing.generatedFrom')}
              <input
                type="date"
                value={exportFilters.startDate}
                onChange={(event) => setExportFilters((current) => ({ ...current, startDate: event.target.value }))}
              />
            </label>

            <label>
              {t('billing.generatedTo')}
              <input
                type="date"
                value={exportFilters.endDate}
                onChange={(event) => setExportFilters((current) => ({ ...current, endDate: event.target.value }))}
              />
            </label>

            <label>
              {t('billing.billedPeriodStart')}
              <input
                type="date"
                value={exportFilters.periodStart}
                onChange={(event) => setExportFilters((current) => ({ ...current, periodStart: event.target.value }))}
              />
            </label>

            <label>
              {t('billing.billedPeriodEnd')}
              <input
                type="date"
                value={exportFilters.periodEnd}
                onChange={(event) => setExportFilters((current) => ({ ...current, periodEnd: event.target.value }))}
              />
            </label>
          </div>

          <button type="button" onClick={refreshTenantData} disabled={loading}>
            {loading ? t('ui.loading') : t('billing.refreshUsage')}
          </button>
          <button type="button" className="billing-secondary-button" onClick={exportTenantCsv} disabled={loading}>
            {t('billing.exportCsv')}
          </button>
          <button type="button" className="billing-secondary-button" onClick={startStripeCheckout} disabled={loading}>
            {t('billing.startCheckout')}
          </button>
          <button type="button" className="billing-secondary-button" onClick={openStripePortal} disabled={loading}>
            {t('billing.managePortal')}
          </button>

          {checkoutState.success ? (
            <p className="billing-note">
              {t('billing.checkoutCompleted')}
              {checkoutState.sessionId ? ` ${t('billing.session')}: ${checkoutState.sessionId}` : ''}
            </p>
          ) : null}
          {checkoutState.canceled ? <p className="billing-note">{t('billing.checkoutCanceled')}</p> : null}

          {error ? <p className="billing-error">{error}</p> : null}

          {usageSummary ? (
            <div className="billing-metrics">
              <p>{t('billing.subscriptionStatus')}: {usageSummary.subscription_status || t('ui.unknown')}</p>
              {usageSummary.grace_period_ends_at ? (
                <p>{t('billing.graceEndsAt')}: {new Date(usageSummary.grace_period_ends_at).toLocaleString(locale === 'es' ? 'es-ES' : 'en-US')}</p>
              ) : null}
              <p>{t('billing.metricActiveUsers')}: {usageSummary.active_users}</p>
              <p>{t('billing.metricApiRequests')}: {usageSummary.api_requests}</p>
              <p>{t('billing.metricOverageUsers')}: {usageSummary.overage_users}</p>
              <p>{t('billing.metricOverageApi')}: {usageSummary.overage_api_requests}</p>
              {usageSummary.latest_invoice ? (
                <p>
                  {t('billing.latestInvoice')}:{' '}
                  <a
                    href={`/api/v1/billing/invoices/${usageSummary.latest_invoice.invoice_id}/receipt.txt`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {t('billing.downloadReceipt')}
                  </a>
                  {' · '}
                  <a
                    href={`/api/v1/billing/invoices/${usageSummary.latest_invoice.invoice_id}/receipt.pdf`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {t('billing.downloadPdf')}
                  </a>
                </p>
              ) : null}
            </div>
          ) : null}

          {estimateResult ? (
            <div className="billing-metrics">
              <p className="billing-metrics__total">
                {t('billing.currentEstimate')}: {formatMoney(estimateResult.total_cents, estimateResult.currency, locale)}
              </p>
            </div>
          ) : null}
        </article>
      </div>
    </section>
  );
}
