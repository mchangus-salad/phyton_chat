from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.utils import timezone

from api.billing import BillingConfigurationError, StripeBillingProvider
from api.models import BillingEvent, BillingInvoice, BillingInvoiceLineItem, Subscription, SubscriptionPlan, Tenant, TenantMembership, UsageRecord
from api.telemetry import incr


@dataclass
class SubscriptionDraftResult:
    tenant: Tenant
    subscription: Subscription


@dataclass
class CheckoutSessionResult:
    tenant: Tenant
    subscription: Subscription
    session: object


@dataclass
class HybridBillingEstimate:
    tenant_id: str
    plan_code: str
    currency: str
    billing_cycle: str
    period_start: datetime
    period_end: datetime
    included_users: int
    included_api_requests: int
    active_users: int
    api_requests: int
    overage_users: int
    overage_api_requests: int
    platform_fee_cents: int
    users_overage_cents: int
    api_overage_cents: int
    total_cents: int


@dataclass
class PlanChangeResult:
    preview: dict
    applied: bool


def list_active_plans() -> list[SubscriptionPlan]:
    return list(SubscriptionPlan.objects.filter(is_active=True).order_by("price_cents"))


def get_active_plan_or_none(plan_code: str) -> SubscriptionPlan | None:
    return SubscriptionPlan.objects.filter(code=plan_code, is_active=True).first()


def ensure_tenant_for_user(*, user, tenant_name: str, tenant_type: str) -> Tenant:
    normalized_name = (tenant_name or "").strip() or (user.username or "tenant")
    tenant, _created = Tenant.objects.get_or_create(
        owner=user,
        name=normalized_name,
        defaults={"tenant_type": tenant_type},
    )
    return tenant


def create_subscription_draft(*, user, tenant_name: str, tenant_type: str, plan: SubscriptionPlan, trial_days: int | None) -> SubscriptionDraftResult:
    tenant = ensure_tenant_for_user(user=user, tenant_name=tenant_name, tenant_type=tenant_type)
    effective_trial_days = plan.trial_days_default if trial_days is None else trial_days
    now = timezone.now()
    trial_ends_at = now + timedelta(days=effective_trial_days)
    subscription = Subscription.objects.create(
        tenant=tenant,
        plan=plan,
        status=Subscription.Status.TRIALING if effective_trial_days > 0 else Subscription.Status.INCOMPLETE,
        trial_ends_at=trial_ends_at if effective_trial_days > 0 else None,
        current_period_start=now,
        current_period_end=trial_ends_at if effective_trial_days > 0 else None,
        provider="internal",
    )
    BillingEvent.objects.create(
        tenant=tenant,
        event_type="subscription_created",
        provider="internal",
        status=subscription.status,
        payload={"plan_code": plan.code, "trial_days": effective_trial_days},
    )
    incr("billing.subscriptions.created")
    incr("billing.events.total")
    return SubscriptionDraftResult(tenant=tenant, subscription=subscription)


def create_checkout_session(*, user, tenant_name: str, tenant_type: str, plan: SubscriptionPlan) -> CheckoutSessionResult:
    tenant = ensure_tenant_for_user(user=user, tenant_name=tenant_name, tenant_type=tenant_type)
    now = timezone.now()
    subscription = Subscription.objects.create(
        tenant=tenant,
        plan=plan,
        status=Subscription.Status.INCOMPLETE,
        current_period_start=now,
        provider="stripe",
    )
    try:
        provider = StripeBillingProvider()
        session = provider.create_checkout_session(
            tenant=tenant,
            subscription=subscription,
            plan=plan,
            user_email=getattr(user, "email", "") or None,
        )
    except BillingConfigurationError:
        subscription.delete()
        raise

    subscription.provider_customer_id = getattr(session, "customer", "") or ""
    subscription.save(update_fields=["provider_customer_id", "updated_at"])
    BillingEvent.objects.create(
        tenant=tenant,
        event_type="checkout_session_created",
        provider="stripe",
        provider_event_id=getattr(session, "id", "") or "",
        status="created",
        payload={"plan_code": plan.code},
    )
    incr("billing.events.total")
    return CheckoutSessionResult(tenant=tenant, subscription=subscription, session=session)


def get_latest_billable_subscription(tenant: Tenant) -> Subscription | None:
    return (
        Subscription.objects.filter(
            tenant=tenant,
            status__in=[Subscription.Status.TRIALING, Subscription.Status.ACTIVE, Subscription.Status.PAST_DUE],
        )
        .select_related("plan")
        .order_by("-updated_at")
        .first()
    )


def estimate_hybrid_monthly_bill(
    *,
    tenant: Tenant,
    plan: SubscriptionPlan,
    active_users: int | None = None,
    api_requests: int | None = None,
) -> HybridBillingEstimate:
    now = timezone.now()
    period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    next_month = (period_start + timedelta(days=32)).replace(day=1)
    period_end = next_month

    # "Active users" defaults to active memberships until event-level user activity is available.
    observed_active_users = (
        TenantMembership.objects.filter(tenant=tenant, is_active=True).values("user_id").distinct().count()
    )
    if active_users is None:
        active_users = observed_active_users

    if api_requests is None:
        api_requests = (
            UsageRecord.objects.filter(
                tenant=tenant,
                metric="api.request",
                timestamp__gte=period_start,
                timestamp__lt=period_end,
            )
            .values_list("quantity", flat=True)
            .iterator()
        )
        api_requests = int(sum(api_requests))

    included_users = int(plan.max_users or 0)
    included_requests = int(plan.max_monthly_requests or 0)

    overage_users = max(int(active_users) - included_users, 0)
    overage_api_requests = max(int(api_requests) - included_requests, 0)

    users_overage_cents = overage_users * int(plan.seat_price_cents or 0)
    api_blocks_1k = (overage_api_requests + 999) // 1000
    api_overage_cents = api_blocks_1k * int(plan.api_overage_per_1000_cents or 0)
    platform_fee_cents = int(plan.price_cents or 0)
    total_cents = platform_fee_cents + users_overage_cents + api_overage_cents

    return HybridBillingEstimate(
        tenant_id=str(tenant.tenant_id),
        plan_code=plan.code,
        currency=plan.currency,
        billing_cycle=plan.billing_cycle,
        period_start=period_start,
        period_end=period_end,
        included_users=included_users,
        included_api_requests=included_requests,
        active_users=int(active_users),
        api_requests=int(api_requests),
        overage_users=overage_users,
        overage_api_requests=overage_api_requests,
        platform_fee_cents=platform_fee_cents,
        users_overage_cents=users_overage_cents,
        api_overage_cents=api_overage_cents,
        total_cents=total_cents,
    )


def close_current_billing_period(*, tenant: Tenant, subscription: Subscription, active_users: int | None = None, api_requests: int | None = None) -> BillingInvoice:
    estimate = estimate_hybrid_monthly_bill(
        tenant=tenant,
        plan=subscription.plan,
        active_users=active_users,
        api_requests=api_requests,
    )
    invoice, _created = BillingInvoice.objects.update_or_create(
        tenant=tenant,
        period_start=estimate.period_start,
        period_end=estimate.period_end,
        defaults={
            "subscription": subscription,
            "currency": estimate.currency,
            "status": BillingInvoice.Status.FINALIZED,
            "platform_fee_cents": estimate.platform_fee_cents,
            "users_overage_cents": estimate.users_overage_cents,
            "api_overage_cents": estimate.api_overage_cents,
            "total_cents": estimate.total_cents,
            "active_users": estimate.active_users,
            "api_requests": estimate.api_requests,
            "overage_users": estimate.overage_users,
            "overage_api_requests": estimate.overage_api_requests,
            "meta": {
                "plan_code": estimate.plan_code,
                "billing_cycle": estimate.billing_cycle,
            },
        },
    )
    BillingEvent.objects.create(
        tenant=tenant,
        event_type="invoice_finalized",
        provider="internal",
        status="finalized",
        payload={
            "invoice_id": str(invoice.invoice_id),
            "total_cents": invoice.total_cents,
        },
    )
    _replace_invoice_line_items(invoice=invoice, subscription=subscription)
    incr("billing.events.total")
    return invoice


def _replace_invoice_line_items(*, invoice: BillingInvoice, subscription: Subscription) -> None:
    plan = subscription.plan
    BillingInvoiceLineItem.objects.filter(invoice=invoice).delete()

    lines: list[BillingInvoiceLineItem] = [
        BillingInvoiceLineItem(
            invoice=invoice,
            code="platform_fee",
            description="Platform base fee",
            quantity=1,
            unit_price_cents=invoice.platform_fee_cents,
            total_price_cents=invoice.platform_fee_cents,
            meta={"plan_code": plan.code},
        ),
        BillingInvoiceLineItem(
            invoice=invoice,
            code="users_overage",
            description="Active user overage",
            quantity=max(invoice.overage_users, 0),
            unit_price_cents=int(plan.seat_price_cents or 0),
            total_price_cents=invoice.users_overage_cents,
            meta={"included_users": int(plan.max_users or 0), "active_users": invoice.active_users},
        ),
        BillingInvoiceLineItem(
            invoice=invoice,
            code="api_overage",
            description="API request overage (per 1000 requests)",
            quantity=(max(invoice.overage_api_requests, 0) + 999) // 1000,
            unit_price_cents=int(plan.api_overage_per_1000_cents or 0),
            total_price_cents=invoice.api_overage_cents,
            meta={"included_requests": int(plan.max_monthly_requests or 0), "api_requests": invoice.api_requests},
        ),
    ]
    BillingInvoiceLineItem.objects.bulk_create(lines)


def create_portal_session(*, subscription: Subscription, return_url: str | None = None):
    provider = StripeBillingProvider()
    return provider.create_customer_portal_session(
        customer_id=subscription.provider_customer_id,
        return_url=return_url,
    )


def change_subscription_plan(*, subscription: Subscription, target_plan: SubscriptionPlan, apply_change: bool) -> PlanChangeResult:
    provider = StripeBillingProvider()
    preview = provider.preview_subscription_plan_change(
        provider_subscription_id=subscription.provider_subscription_id,
        new_price_id=target_plan.provider_price_id,
    )
    if not apply_change:
        return PlanChangeResult(preview=preview, applied=False)

    provider.apply_subscription_plan_change(
        provider_subscription_id=subscription.provider_subscription_id,
        new_price_id=target_plan.provider_price_id,
    )
    subscription.plan = target_plan
    subscription.save(update_fields=["plan", "updated_at"])
    BillingEvent.objects.create(
        tenant=subscription.tenant,
        event_type="subscription_plan_changed",
        provider="stripe",
        status="applied",
        payload={
            "subscription_id": subscription.pk,
            "target_plan_code": target_plan.code,
            "preview": preview,
        },
    )
    incr("billing.events.total")
    return PlanChangeResult(preview=preview, applied=True)