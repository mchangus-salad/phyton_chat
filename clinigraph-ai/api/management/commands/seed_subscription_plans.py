from django.core.management.base import BaseCommand

from api.models import SubscriptionPlan


DEFAULT_PLANS = [
    {
        "code": "individual-monthly",
        "name": "Individual Monthly",
        "description": "Hybrid billing: platform fee + seat overage + API overage for individual practitioners.",
        "billing_cycle": SubscriptionPlan.BillingCycle.MONTHLY,
        "price_cents": 4900,
        "billing_model": "hybrid",
        "currency": "USD",
        "trial_days_default": 15,
        "max_monthly_requests": 5000,
        "max_users": 1,
        "seat_price_cents": 2900,
        "api_overage_per_1000_cents": 120,
    },
    {
        "code": "clinic-monthly",
        "name": "Clinic Monthly",
        "description": "Hybrid billing for clinics: base org fee, included seats and included API, then overage.",
        "billing_cycle": SubscriptionPlan.BillingCycle.MONTHLY,
        "price_cents": 29900,
        "billing_model": "hybrid",
        "currency": "USD",
        "trial_days_default": 30,
        "max_monthly_requests": 50000,
        "max_users": 25,
        "seat_price_cents": 1900,
        "api_overage_per_1000_cents": 90,
    },
    {
        "code": "hospital-annual",
        "name": "Hospital Annual",
        "description": "Enterprise hybrid billing with annual commitment and high included capacity.",
        "billing_cycle": SubscriptionPlan.BillingCycle.ANNUAL,
        "price_cents": 249900,
        "billing_model": "hybrid",
        "currency": "USD",
        "trial_days_default": 30,
        "max_monthly_requests": 500000,
        "max_users": 500,
        "seat_price_cents": 1200,
        "api_overage_per_1000_cents": 40,
    },
]


class Command(BaseCommand):
    help = "Seed default subscription plans for SaaS billing."

    def handle(self, *args, **options):
        created = 0
        updated = 0
        for item in DEFAULT_PLANS:
            obj, was_created = SubscriptionPlan.objects.update_or_create(
                code=item["code"],
                defaults=item,
            )
            if was_created:
                created += 1
                self.stdout.write(self.style.SUCCESS(f"Created plan {obj.code}"))
            else:
                updated += 1
                self.stdout.write(f"Updated plan {obj.code}")

        self.stdout.write(self.style.SUCCESS(f"seed_subscription_plans done created={created} updated={updated}"))
