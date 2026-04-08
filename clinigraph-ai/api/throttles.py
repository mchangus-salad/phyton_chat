from django.db.models import Sum
from django.utils import timezone
from rest_framework.throttling import AnonRateThrottle, BaseThrottle, UserRateThrottle


class AgentAnonRateThrottle(AnonRateThrottle):
    scope = "agent_anon"


class AgentUserRateThrottle(UserRateThrottle):
    scope = "agent_user"


class TenantPlanQuotaThrottle(BaseThrottle):
    """Hard quota throttle based on the tenant's active subscription plan.

    Blocks agent requests once the tenant has consumed
    OVERAGE_MULTIPLIER * plan.max_monthly_requests API calls within the
    current calendar month (tracked via UsageRecord metric='api_requests').
    Allows up to 2x the plan limit before hard-blocking to absorb brief spikes.
    When no tenant or no active subscription is found the check is skipped —
    other permission classes handle access control in those cases.
    """

    OVERAGE_MULTIPLIER: float = 2.0

    def allow_request(self, request, view) -> bool:
        from api.models import Subscription, UsageRecord

        tenant = getattr(request, "tenant", None)
        if tenant is None:
            return True

        subscription = (
            Subscription.objects.filter(
                tenant=tenant,
                status__in=[
                    Subscription.Status.ACTIVE,
                    Subscription.Status.TRIALING,
                    Subscription.Status.PAST_DUE,
                ],
            )
            .select_related("plan")
            .order_by("-created_at")
            .first()
        )
        if subscription is None:
            return True

        max_requests = subscription.plan.max_monthly_requests
        if max_requests == 0:
            return True  # unlimited plan

        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        result = UsageRecord.objects.filter(
            tenant=tenant,
            metric="api_requests",
            timestamp__gte=start_of_month,
        ).aggregate(total=Sum("quantity"))
        current_count = int(result.get("total") or 0)

        self._current = current_count
        self._limit = int(max_requests * self.OVERAGE_MULTIPLIER)
        return current_count < self._limit

    def wait(self):
        return None  # quota exhaustion — no retry-after hint

    def throttle_failure_message(self) -> str:
        current = getattr(self, "_current", 0)
        limit = getattr(self, "_limit", 0)
        return (
            f"Monthly API quota exceeded ({current}/{limit} requests used). "
            "Upgrade your plan or wait for the next billing period."
        )
