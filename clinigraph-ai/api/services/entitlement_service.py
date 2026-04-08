"""
Entitlement service — single source of truth for subscription access control.

Lifecycle:
  TRIALING / ACTIVE          → full access
  PAST_DUE (within grace)    → access allowed + warning header
  PAST_DUE (grace expired)   → access denied (402)
  CANCELED / INCOMPLETE      → access denied (402)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from ..models import Subscription, Tenant

logger = logging.getLogger(__name__)

_GRACE_DAYS = lambda: int(getattr(settings, "BILLING_GRACE_PERIOD_DAYS", 7))  # noqa: E731


# ---------------------------------------------------------------------------
# Result value object
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EntitlementResult:
    allowed: bool
    status: str               # mirrors Subscription.Status or "no_subscription"
    in_grace: bool = False
    grace_ends_at: datetime | None = None


# ---------------------------------------------------------------------------
# Core check
# ---------------------------------------------------------------------------

def check_tenant_entitlement(tenant: Tenant) -> EntitlementResult:
    """Return whether *tenant* is allowed to use the service right now."""
    sub = (
        Subscription.objects
        .filter(tenant=tenant)
        .order_by("-updated_at")
        .first()
    )
    if sub is None:
        return EntitlementResult(allowed=False, status="no_subscription")

    s = sub.status

    if s in (Subscription.Status.TRIALING, Subscription.Status.ACTIVE):
        return EntitlementResult(allowed=True, status=s)

    if s == Subscription.Status.PAST_DUE:
        if sub.grace_period_ends_at and sub.grace_period_ends_at > timezone.now():
            return EntitlementResult(
                allowed=True,
                status=s,
                in_grace=True,
                grace_ends_at=sub.grace_period_ends_at,
            )
        return EntitlementResult(allowed=False, status="grace_expired")

    # CANCELED, INCOMPLETE, or anything else
    return EntitlementResult(allowed=False, status=s)


# ---------------------------------------------------------------------------
# State transitions used by webhook + management command
# ---------------------------------------------------------------------------

def begin_grace_period(subscription: Subscription) -> Subscription:
    """Mark subscription PAST_DUE and open a grace window.

    Idempotent: if a grace window is already set and still in the future, it
    is *not* reset.  This prevents payment retries from extending the grace
    period each time Stripe fires another ``invoice.payment_failed`` event.
    """
    grace_days = _GRACE_DAYS()
    update_fields = ["status", "updated_at"]

    subscription.status = Subscription.Status.PAST_DUE

    if not subscription.grace_period_ends_at:
        subscription.grace_period_ends_at = timezone.now() + timezone.timedelta(days=grace_days)
        update_fields.append("grace_period_ends_at")
        logger.info(
            "grace_period_started tenant=%s sub=%s ends_at=%s",
            subscription.tenant_id,
            subscription.pk,
            subscription.grace_period_ends_at.isoformat(),
        )
    else:
        logger.info(
            "grace_period_retained tenant=%s sub=%s ends_at=%s",
            subscription.tenant_id,
            subscription.pk,
            subscription.grace_period_ends_at.isoformat(),
        )

    subscription.save(update_fields=update_fields)
    return subscription


def restore_entitlement(subscription: Subscription) -> Subscription:
    """Mark subscription ACTIVE and clear any grace window and failure counter."""
    subscription.status = Subscription.Status.ACTIVE
    subscription.grace_period_ends_at = None
    subscription.failed_payment_count = 0
    subscription.save(update_fields=["status", "grace_period_ends_at", "failed_payment_count", "updated_at"])
    logger.info("entitlement_restored tenant=%s sub=%s", subscription.tenant_id, subscription.pk)
    return subscription


def revoke_entitlement(subscription: Subscription) -> Subscription:
    """Cancel subscription immediately and clear failure counter."""
    subscription.status = Subscription.Status.CANCELED
    subscription.canceled_at = timezone.now()
    subscription.grace_period_ends_at = None
    subscription.failed_payment_count = 0
    subscription.save(update_fields=["status", "canceled_at", "grace_period_ends_at", "failed_payment_count", "updated_at"])
    logger.info("entitlement_revoked tenant=%s sub=%s", subscription.tenant_id, subscription.pk)
    return subscription


def increment_failed_payment_count(subscription: Subscription) -> int:
    """Atomically increment ``failed_payment_count`` and return the new value."""
    from django.db.models import F  # local import to avoid circular at module level

    Subscription.objects.filter(pk=subscription.pk).update(
        failed_payment_count=F("failed_payment_count") + 1
    )
    subscription.refresh_from_db(fields=["failed_payment_count"])
    logger.info(
        "failed_payment_count_incremented tenant=%s sub=%s count=%s",
        subscription.tenant_id,
        subscription.pk,
        subscription.failed_payment_count,
    )
    return subscription.failed_payment_count


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

_NOTIFICATION_TEMPLATES: dict[str, tuple[str, str]] = {
    "payment_failed": (
        "Action required: payment failed for your CliniGraph subscription",
        (
            "Your recent payment failed.\n\n"
            "Your account has a {grace_days}-day grace period — the service remains available "
            "until {grace_ends_at}. Please update your billing information to avoid interruption.\n\n"
            "Visit your billing portal: {portal_url}"
        ),
    ),
    "payment_action_required": (
        "Action required: authentication needed to complete your CliniGraph payment",
        (
            "Your recent payment requires additional authentication (e.g. 3D Secure).\n\n"
            "Please visit your billing portal to complete the payment and avoid service interruption.\n\n"
            "Visit your billing portal: {portal_url}"
        ),
    ),
    "service_suspended": (
        "Your CliniGraph service has been suspended",
        (
            "Your grace period has ended and your subscription has been suspended "
            "due to an outstanding payment.\n\n"
            "To restore access, please update your billing information and renew your subscription.\n\n"
            "Visit your billing portal: {portal_url}"
        ),
    ),
    "payment_recovered": (
        "Your CliniGraph service has been restored",
        (
            "Great news — your payment was processed successfully and your service has been fully restored.\n\n"
            "Thank you for being a CliniGraph customer."
        ),
    ),
    "subscription_canceled": (
        "Your CliniGraph subscription has been canceled",
        (
            "Your subscription has been canceled. Access to the service has been removed.\n\n"
            "If you have questions or would like to reactivate, please contact support."
        ),
    ),
    "trial_expired": (
        "Your CliniGraph trial has expired",
        (
            "Your free trial has ended.\n\n"
            "Your account has a {grace_days}-day grace period — the service remains available "
            "until {grace_ends_at}. Add a payment method to continue using CliniGraph.\n\n"
            "Visit your billing portal: {portal_url}"
        ),
    ),
    "trial_converted_active": (
        "Your CliniGraph trial has converted to an active subscription",
        (
            "Great news — your free trial has automatically converted to an active subscription "
            "at no charge.\n\n"
            "You now have full access to all CliniGraph features."
        ),
    ),
    "trial_will_end": (
        "Your CliniGraph trial is ending soon",
        (
            "Your free trial is ending soon.\n\n"
            "Add a payment method before your trial expires to continue using CliniGraph without interruption.\n\n"
            "Visit your billing portal: {portal_url}"
        ),
    ),
}


def notify_subscription_event(
    tenant: Tenant,
    event_type: str,
    subscription: Subscription | None = None,
) -> None:
    """
    Send an email notification to the tenant owner for a subscription lifecycle event.

    event_type one of: payment_failed, service_suspended, payment_recovered, subscription_canceled
    """
    if event_type not in _NOTIFICATION_TEMPLATES:
        logger.warning("notify_subscription_event: unknown event_type=%s", event_type)
        return

    owner = tenant.owner
    if owner is None or not owner.email:
        logger.info(
            "notify_subscription_event: skipped (no owner email) tenant=%s event=%s",
            tenant.tenant_id,
            event_type,
        )
        return

    subject_tmpl, body_tmpl = _NOTIFICATION_TEMPLATES[event_type]

    portal_url = getattr(settings, "STRIPE_BILLING_PORTAL_RETURN_URL", "")
    grace_days = _GRACE_DAYS()
    grace_ends_at = (
        subscription.grace_period_ends_at.strftime("%Y-%m-%d %H:%M UTC")
        if subscription and subscription.grace_period_ends_at
        else "N/A"
    )

    body = body_tmpl.format(
        grace_days=grace_days,
        grace_ends_at=grace_ends_at,
        portal_url=portal_url or "https://app.clinigraph.ai/billing",
    )

    try:
        send_mail(
            subject=subject_tmpl,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[owner.email],
            fail_silently=True,
        )
        logger.info(
            "notification_sent tenant=%s event=%s recipient=%s",
            tenant.tenant_id,
            event_type,
            owner.email,
        )
    except Exception:
        logger.exception(
            "notification_failed tenant=%s event=%s",
            tenant.tenant_id,
            event_type,
        )
