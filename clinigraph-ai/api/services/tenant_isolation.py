"""
Tenant isolation strategy for CliniGraph AI.

All data access on tenant-owned models MUST use the TenantBoundManager
(exposed as Model.tenant_objects) to prevent accidental cross-tenant data
leakage.  The default `objects` manager is intentionally left intact so
that Django admin, management commands, and migrations work without
modification.

Usage
-----
Scoped queryset (preferred pattern)::

    sessions = AgentChatSession.tenant_objects.for_tenant(tenant)
    invoice  = BillingInvoice.tenant_objects.for_tenant(tenant).filter(invoice_id=pk).first()

Ownership assertion (for objects fetched by external/non-tenant key)::

    subscription = Subscription.objects.filter(provider_subscription_id=sid).first()
    if subscription:
        assert_tenant_owns(subscription, tenant)  # raises PermissionError if mismatch
"""

from __future__ import annotations

from django.db import models


class TenantBoundQuerySet(models.QuerySet):
    """QuerySet that exposes a .for_tenant() scoping method."""

    def for_tenant(self, tenant: object) -> "TenantBoundQuerySet":
        """Return only records belonging to *tenant*."""
        return self.filter(tenant=tenant)


class TenantBoundManager(models.Manager):
    """
    Additional manager for tenant-owned models.

    Attach to any model that has a ``tenant`` ForeignKey::

        class MyModel(models.Model):
            tenant = models.ForeignKey(Tenant, ...)
            objects = models.Manager()          # keep default for admin / migrations
            tenant_objects = TenantBoundManager()  # scoped — use in application code
    """

    def get_queryset(self) -> TenantBoundQuerySet:
        return TenantBoundQuerySet(self.model, using=self._db)

    def for_tenant(self, tenant: object) -> TenantBoundQuerySet:
        """Shortcut: ``Model.tenant_objects.for_tenant(tenant)``."""
        return self.get_queryset().for_tenant(tenant)


def assert_tenant_owns(obj: object, tenant: object) -> None:
    """
    Raise ``PermissionError`` if *obj* does not belong to *tenant*.

    Intended for objects fetched by an external identifier (e.g. a Stripe
    subscription ID) where the ORM queryset could not be pre-scoped.

    :param obj:    A Django model instance with a ``tenant_id`` attribute.
    :param tenant: The ``Tenant`` instance that must own *obj*.
    :raises PermissionError: When ownership cannot be confirmed.
    """
    obj_tenant_id = getattr(obj, "tenant_id", None)
    if obj_tenant_id is None:
        raise PermissionError(
            f"{type(obj).__name__} has no 'tenant_id' attribute — "
            "it may not be a tenant-owned model."
        )
    if obj_tenant_id != tenant.pk:
        raise PermissionError(
            f"Cross-tenant access denied: {type(obj).__name__}(pk={getattr(obj, 'pk', '?')}) "
            f"belongs to tenant {obj_tenant_id!r}, not {tenant.pk!r}."
        )
