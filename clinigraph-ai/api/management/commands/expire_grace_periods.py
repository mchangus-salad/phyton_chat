"""
Management command: expire_grace_periods

Finds all subscriptions in PAST_DUE status whose grace window has elapsed
and revokes their entitlement (sets CANCELED).  Intended to be run as a
periodic cron job or scheduled task (e.g. every hour).

Usage:
    python manage.py expire_grace_periods
    python manage.py expire_grace_periods --dry-run
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from api.models import Subscription
from api.services.entitlement_service import notify_subscription_event, revoke_entitlement


class Command(BaseCommand):
    help = "Cancel subscriptions whose grace period has expired."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be canceled without making changes.",
        )

    def handle(self, *args, **options):
        dry_run: bool = options["dry-run"] if "dry-run" in options else options.get("dry_run", False)
        now = timezone.now()

        expired_qs = Subscription.objects.filter(
            status=Subscription.Status.PAST_DUE,
            grace_period_ends_at__lte=now,
            provider="internal",
        ).select_related("tenant", "tenant__owner")

        count = 0
        for sub in expired_qs:
            tenant = sub.tenant
            if dry_run:
                self.stdout.write(
                    f"[dry-run] Would cancel sub={sub.pk} tenant={tenant.name} "
                    f"grace_ended={sub.grace_period_ends_at}"
                )
            else:
                revoke_entitlement(sub)
                notify_subscription_event(tenant, "service_suspended", sub)
                self.stdout.write(
                    self.style.WARNING(
                        f"Canceled sub={sub.pk} tenant={tenant.name}"
                    )
                )
            count += 1

        summary = f"{'[dry-run] ' if dry_run else ''}Processed {count} expired grace period(s)."
        self.stdout.write(self.style.SUCCESS(summary))
