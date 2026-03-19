import secrets

from django.conf import settings
from rest_framework.permissions import BasePermission


class HasAgentApiKeyOrAuthenticated(BasePermission):
    """Allow access when request is authenticated with JWT/session or has a valid API key."""

    message = "Authentication required: provide a valid bearer token or X-API-Key"

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            return True

        expected = (getattr(settings, "AGENT_API_KEY", "") or "").strip()
        if not expected:
            return False

        provided = (request.headers.get("X-API-Key") or "").strip()
        if not provided:
            return False
        return secrets.compare_digest(provided, expected)
