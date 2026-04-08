"""Tax and VAT calculation service for CliniGraph AI internal billing.

Strategy
--------
- Tenants flagged as ``tax_exempt`` pay no tax.
- Tax jurisdiction is resolved from ``tenant.tax_country_code`` +
  ``tenant.tax_region_code`` against the ``TaxPolicy`` table.
- Region-specific policies (region_code != '') take precedence over
  country-wide policies (region_code == '').
- ``is_inclusive`` means the declared price already contains tax:
  no extra cents are added, but the rate is stored for invoice reporting.
- For Stripe-managed subscriptions, Stripe Tax handles calculation
  automatically when ``automatic_tax`` is enabled on the checkout session.
  This service covers **internal-provider** subscriptions only.

Basis points (bps)
------------------
  10 000 bps = 100 %
   2 000 bps =  20 % (EU standard VAT)
     825 bps =  8.25 % (US Texas SaaS rate)
"""
from __future__ import annotations

from django.db.models import Q

from api.models import TaxPolicy, Tenant


def calculate_tax_for_subtotal(subtotal_cents: int, tenant: Tenant) -> tuple[int, int]:
    """Return ``(tax_cents, rate_bps)`` for the given subtotal and tenant.

    - ``(0, 0)`` when the tenant is tax-exempt or has no country code set.
    - ``(0, rate_bps)`` for inclusive-tax policies (no extra charge, rate recorded).
    - ``(tax_cents, rate_bps)`` otherwise, where
      ``tax_cents = floor(subtotal_cents * rate_bps / 10_000)``.
    """
    if tenant.tax_exempt:
        return 0, 0

    country = (tenant.tax_country_code or "").strip().upper()
    if not country:
        return 0, 0

    region = (tenant.tax_region_code or "").strip().upper()

    # Prefer region-specific policy; fall back to country-wide (region_code='').
    policy = (
        TaxPolicy.objects.filter(
            country_code=country,
            is_active=True,
        )
        .filter(Q(region_code=region) | Q(region_code=""))
        .order_by("-region_code")  # non-empty region sorts first
        .first()
    )

    if policy is None:
        return 0, 0

    if policy.is_inclusive:
        # Tax is already embedded in the price — record the rate but add nothing.
        return 0, policy.rate_bps

    tax_cents = (subtotal_cents * policy.rate_bps) // 10_000
    return tax_cents, policy.rate_bps
