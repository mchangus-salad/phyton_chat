"""
Management command: expire_trials

Finds all internal-provider TRIALING subscriptions whose ``trial_ends_at``
has elapsed and converts them:

  - Free plans (price_cents == 0): TRIALING → ACTIVE  (trial converts automatically)
  - Paid plans (price_cents > 0):  TRIALING → PAST_DUE (user must add payment)

Stripe-provider subscriptions are intentionally skipped; Stripe drives those
transitions via webhooks (``customer.subscription.updated``).

Intended to run hourly as a cron/scheduled task:
    python manage.py expire_trials
    python manage.py expire_trials --dry-run
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from api.models import Subscription
from api.services.entitlement_service import begin_grace_period, notify_subscription_event


class Command(BaseCommand):
    help = "Convert expired TRIALING subscriptions to ACTIVE or PAST_DUE."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would change without saving to the database.",
        )

    def handle(self, *args, **options):
        dry_run: bool = options.get("dry_run", False)
        now = timezone.now()

        expired_qs = (
            Subscription.objects.filter(
                status=Subscription.Status.TRIALING,
                trial_ends_at__lte=now,
                provider="internal",
            )
            .select_related("tenant", "tenant__owner", "plan")
        )

        converted_free = 0
        converted_paid = 0

        for sub in expired_qs:
            tenant = sub.tenant
            is_free_plan = sub.plan.price_cents == 0

            if dry_run:
                target = "ACTIVE" if is_free_plan else "PAST_DUE"
                self.stdout.write(
                    f"[dry-run] sub={sub.pk} tenant={tenant.name} "
                    f"trial_ended={sub.trial_ends_at} → {target}"
                )
                if is_free_plan:
                    converted_free += 1
                else:
                    converted_paid += 1
                continue

            if is_free_plan:
                # Free plan: trial converts seamlessly to active.
                sub.status = Subscription.Status.ACTIVE
                sub.trial_ends_at = None
                sub.save(update_fields=["status", "trial_ends_at", "updated_at"])
                notify_subscription_event(tenant, "trial_converted_active", sub)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Converted sub={sub.pk} tenant={tenant.name} → ACTIVE (free plan)"
                    )
                )
                converted_free += 1
            else:
                # Paid plan: trial expired without payment; enter grace period.
                begin_grace_period(sub)
                notify_subscription_event(tenant, "trial_expired", sub)
                self.stdout.write(
                    self.style.WARNING(
                        f"Trial expired sub={sub.pk} tenant={tenant.name} → PAST_DUE (grace period started)"
                    )
                )
                converted_paid += 1

        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Processed {converted_free + converted_paid} trial(s): "
                f"{converted_free} converted to ACTIVE, {converted_paid} moved to PAST_DUE."
            )
        )
