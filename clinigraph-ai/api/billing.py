from __future__ import annotations

import os
from datetime import datetime


class BillingConfigurationError(RuntimeError):
    pass


class StripeBillingProvider:
    def __init__(self):
        try:
            import stripe  # type: ignore[import]
        except ImportError as exc:
            raise BillingConfigurationError("Stripe package is not installed") from exc

        secret_key = (os.getenv("STRIPE_SECRET_KEY", "") or "").strip()
        if not secret_key:
            raise BillingConfigurationError("STRIPE_SECRET_KEY is not configured")

        self.stripe = stripe
        self.stripe.api_key = secret_key
        self.success_url = (os.getenv("STRIPE_CHECKOUT_SUCCESS_URL", "") or "").strip()
        self.cancel_url = (os.getenv("STRIPE_CHECKOUT_CANCEL_URL", "") or "").strip()
        self.portal_return_url = (os.getenv("STRIPE_BILLING_PORTAL_RETURN_URL", "") or "").strip()
        self.webhook_secret = (os.getenv("STRIPE_WEBHOOK_SECRET", "") or "").strip()

    def create_checkout_session(self, *, tenant, subscription, plan, user_email: str | None, existing_customer_id: str | None = None) -> object:
        if not plan.provider_price_id:
            raise BillingConfigurationError(f"Plan '{plan.code}' does not have provider_price_id configured")
        if not self.success_url or not self.cancel_url:
            raise BillingConfigurationError("STRIPE_CHECKOUT_SUCCESS_URL / STRIPE_CHECKOUT_CANCEL_URL are not configured")

        metadata = {
            "tenant_id": str(tenant.tenant_id),
            "subscription_id": str(subscription.pk),
            "plan_code": plan.code,
        }
        payload = {
            "mode": "subscription",
            "success_url": self.success_url,
            "cancel_url": self.cancel_url,
            "line_items": [{"price": plan.provider_price_id, "quantity": 1}],
            "client_reference_id": str(tenant.tenant_id),
            "subscription_data": {"trial_period_days": int(plan.trial_days_default), "metadata": metadata},
            "metadata": metadata,
        }
        if existing_customer_id:
            payload["customer"] = existing_customer_id
        elif user_email:
            payload["customer_email"] = user_email
        return self.stripe.checkout.Session.create(
            **payload,
        )

    def construct_event(self, payload: bytes, signature_header: str | None):
        if not self.webhook_secret:
            raise BillingConfigurationError("STRIPE_WEBHOOK_SECRET is not configured")
        return self.stripe.Webhook.construct_event(payload=payload, sig_header=signature_header, secret=self.webhook_secret)

    def create_customer_portal_session(self, *, customer_id: str, return_url: str | None = None):
        if not customer_id:
            raise BillingConfigurationError("Stripe customer id is required")
        resolved_return_url = (return_url or self.portal_return_url or self.success_url or "").strip()
        if not resolved_return_url:
            raise BillingConfigurationError("STRIPE_BILLING_PORTAL_RETURN_URL or STRIPE_CHECKOUT_SUCCESS_URL is not configured")
        return self.stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=resolved_return_url,
        )

    def preview_subscription_plan_change(self, *, provider_subscription_id: str, new_price_id: str):
        if not provider_subscription_id:
            raise BillingConfigurationError("provider subscription id is required")
        if not new_price_id:
            raise BillingConfigurationError("new Stripe price id is required")

        subscription = self.stripe.Subscription.retrieve(provider_subscription_id)
        items = list(getattr(subscription, "items", {}).get("data", []))
        if not items:
            raise BillingConfigurationError("Stripe subscription has no items")
        first_item = items[0]
        proration_ts = int(datetime.utcnow().timestamp())
        upcoming = self.stripe.Invoice.upcoming(
            subscription=provider_subscription_id,
            subscription_items=[{"id": first_item.id, "price": new_price_id}],
            subscription_proration_date=proration_ts,
        )
        return {
            "currency": getattr(upcoming, "currency", "usd"),
            "amount_due": int(getattr(upcoming, "amount_due", 0) or 0),
            "amount_remaining": int(getattr(upcoming, "amount_remaining", 0) or 0),
            "proration_date": proration_ts,
        }

    def apply_subscription_plan_change(self, *, provider_subscription_id: str, new_price_id: str):
        if not provider_subscription_id:
            raise BillingConfigurationError("provider subscription id is required")
        if not new_price_id:
            raise BillingConfigurationError("new Stripe price id is required")

        subscription = self.stripe.Subscription.retrieve(provider_subscription_id)
        items = list(getattr(subscription, "items", {}).get("data", []))
        if not items:
            raise BillingConfigurationError("Stripe subscription has no items")
        first_item = items[0]
        return self.stripe.Subscription.modify(
            provider_subscription_id,
            items=[{"id": first_item.id, "price": new_price_id}],
            proration_behavior="create_prorations",
        )
