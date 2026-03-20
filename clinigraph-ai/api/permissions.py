import secrets

from django.conf import settings
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


class IsTenantClinicianOrAbove(HasTenantRole):
    allowed_roles = (
        TenantMembership.Role.OWNER,
        TenantMembership.Role.ADMIN,
        TenantMembership.Role.CLINICIAN,
    )
