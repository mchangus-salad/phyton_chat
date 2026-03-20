import secrets

from django.conf import settings
from rest_framework.exceptions import APIException
from rest_framework.permissions import BasePermission

from .models import TenantMembership
from .security import record_security_event
from .telemetry import incr


class HasAgentApiKeyOrAuthenticated(BasePermission):
    """Allow access when request is authenticated with JWT/session or has a valid API key."""

    message = "Authentication required: provide a valid bearer token or X-API-Key"

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            return True

        expected = (getattr(settings, "AGENT_API_KEY", "") or "").strip()
        if not expected:
            incr("auth.failures.total")
            return False

        provided = (request.headers.get("X-API-Key") or "").strip()
        if not provided:
            incr("auth.failures.total")
            return False
        if secrets.compare_digest(provided, expected):
            return True

        incr("auth.failures.total")
        ip = (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR"))
        record_security_event(
            event_type="invalid_api_key",
            severity="medium",
            ip_address=ip,
            path=request.path,
            method=request.method,
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            user=user,
            meta={"view": view.__class__.__name__},
        )
        return False


class HasTenantRole(BasePermission):
    """Base permission for endpoints that require a tenant role from X-Tenant-ID."""

    allowed_roles: tuple[str, ...] = ()
    tenant_header = "X-Tenant-ID"
    message = "A valid tenant membership with sufficient privileges is required"

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False

        tenant_id = (request.headers.get(self.tenant_header) or "").strip()
        if not tenant_id:
            return False

        membership = TenantMembership.objects.filter(
            user=user,
            tenant__tenant_id=tenant_id,
            is_active=True,
            role__in=self.allowed_roles,
            tenant__is_active=True,
        ).first()
        if not membership:
            return False

        request.tenant = membership.tenant
        request.tenant_membership = membership
        return True


class IsTenantAdminOrOwner(HasTenantRole):
    allowed_roles = (TenantMembership.Role.OWNER, TenantMembership.Role.ADMIN)


class IsTenantBillingAdminOrOwner(HasTenantRole):
    allowed_roles = (
        TenantMembership.Role.OWNER,
        TenantMembership.Role.ADMIN,
        TenantMembership.Role.BILLING,
    )


class IsTenantClinicianOrAbove(HasTenantRole):
    allowed_roles = (
        TenantMembership.Role.OWNER,
        TenantMembership.Role.ADMIN,
        TenantMembership.Role.CLINICIAN,
    )


class SubscriptionRequired(APIException):
    """Raised when a tenant's subscription is not active. Returns HTTP 402."""
    status_code = 402
    default_code = "subscription_required"
    default_detail = "An active subscription is required to access this resource."


class HasActiveEntitlement(BasePermission):
    """
    Enforce subscription entitlement for tenant-scoped endpoints.

    Must be listed **after** a HasTenantRole subclass in permission_classes so
    that request.tenant is already populated.

    Behaviour:
    - ACTIVE / TRIALING                       → allow
    - PAST_DUE within grace period            → allow + sets request._entitlement_warning
    - PAST_DUE (grace expired) / CANCELED     → raises SubscriptionRequired (HTTP 402)
    - No subscription found                   → raises SubscriptionRequired (HTTP 402)
    """

    _STATUS_MESSAGES = {
        "no_subscription": "No active subscription found for this tenant.",
        "grace_expired": "Your payment grace period has expired. Please update your billing information.",
        "canceled": "Your subscription has been canceled. Please renew to restore access.",
        "incomplete": "Your subscription setup is incomplete. Please complete the checkout process.",
    }

    def has_permission(self, request, view):
        from .services.entitlement_service import check_tenant_entitlement  # avoid circular import

        tenant = getattr(request, "tenant", None)
        if tenant is None:
            raise SubscriptionRequired(detail="Tenant context is missing.")

        result = check_tenant_entitlement(tenant)
        if result.allowed:
            if result.in_grace:
                # Views can inspect this to add a warning header / payload note
                request._entitlement_warning = result.grace_ends_at
            return True

        detail = self._STATUS_MESSAGES.get(
            result.status,
            f"Subscription access denied (status: {result.status}).",
        )
        raise SubscriptionRequired(detail=detail)


class HasLlmAccessOrApiKey(BasePermission):
    """
    Allow LLM endpoints for API-key automation and tenant users with active entitlement.

    Rule:
    - Valid X-API-Key path: allowed (service-to-service automation)
    - Authenticated users must provide X-Tenant-ID and belong to tenant as owner/admin/clinician
    - Authenticated users are subject to HasActiveEntitlement for that tenant
    - Billing/auditor users are denied for LLM endpoints
    """

    message = "Tenant-scoped LLM access requires owner/admin/clinician role and active entitlement."

    def has_permission(self, request, view):
        base = HasAgentApiKeyOrAuthenticated()
        if not base.has_permission(request, view):
            return False

        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            # Access granted by API key path.
            return True

        tenant_permission = IsTenantClinicianOrAbove()
        if not tenant_permission.has_permission(request, view):
            return False

        entitlement_permission = HasActiveEntitlement()
        return entitlement_permission.has_permission(request, view)
