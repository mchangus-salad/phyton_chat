from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from api.models import Tenant, TenantMembership


DEFAULT_PASSWORD = "LocalDev123!"
DEFAULT_TENANT_NAME = "Local Dev Clinic"

ROLE_USERS = [
    {
        "username": "local-owner",
        "email": "local-owner@clinigraph.local",
        "role": TenantMembership.Role.OWNER,
        "description": "Platform owner for tenant administration.",
    },
    {
        "username": "local-admin",
        "email": "local-admin@clinigraph.local",
        "role": TenantMembership.Role.ADMIN,
        "description": "Operational admin for tenant and usage management.",
    },
    {
        "username": "local-billing",
        "email": "local-billing@clinigraph.local",
        "role": TenantMembership.Role.BILLING,
        "description": "Billing operator (no LLM access).",
    },
    {
        "username": "local-clinician",
        "email": "local-clinician@clinigraph.local",
        "role": TenantMembership.Role.CLINICIAN,
        "description": "Clinical user with LLM clinical workflow access.",
    },
    {
        "username": "local-auditor",
        "email": "local-auditor@clinigraph.local",
        "role": TenantMembership.Role.AUDITOR,
        "description": "Read-oriented auditor role for tenant controls.",
    },
]


class Command(BaseCommand):
    help = "Seed local development users: one account per tenant role."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            type=str,
            default=DEFAULT_PASSWORD,
            help="Password to assign to all local role users.",
        )
        parser.add_argument(
            "--tenant-name",
            type=str,
            default=DEFAULT_TENANT_NAME,
            help="Tenant name used for local role memberships.",
        )

    def handle(self, *args, **options):
        password = options["password"]
        tenant_name = options["tenant_name"]

        User = get_user_model()

        owner_cfg = next(item for item in ROLE_USERS if item["role"] == TenantMembership.Role.OWNER)
        owner_user, owner_created = User.objects.get_or_create(
            username=owner_cfg["username"],
            defaults={"email": owner_cfg["email"]},
        )
        if owner_user.email != owner_cfg["email"]:
            owner_user.email = owner_cfg["email"]
        owner_user.set_password(password)
        owner_user.save()

        tenant, tenant_created = Tenant.objects.get_or_create(
            name=tenant_name,
            defaults={
                "tenant_type": Tenant.Type.CLINIC,
                "owner": owner_user,
            },
        )
        if tenant.owner_id != owner_user.id:
            tenant.owner = owner_user
            tenant.save(update_fields=["owner", "updated_at"])

        created_users = 1 if owner_created else 0
        updated_users = 0 if owner_created else 1
        created_memberships = 0
        updated_memberships = 0

        for config in ROLE_USERS:
            user, user_created = User.objects.get_or_create(
                username=config["username"],
                defaults={"email": config["email"]},
            )
            if user.email != config["email"]:
                user.email = config["email"]
            user.set_password(password)
            user.save()

            if user_created:
                created_users += 1
            elif user.username != owner_cfg["username"]:
                updated_users += 1

            membership, membership_created = TenantMembership.objects.update_or_create(
                tenant=tenant,
                user=user,
                defaults={
                    "role": config["role"],
                    "is_active": True,
                },
            )
            if membership_created:
                created_memberships += 1
                self.stdout.write(self.style.SUCCESS(f"Created membership {user.username} -> {membership.role}"))
            else:
                updated_memberships += 1
                self.stdout.write(f"Updated membership {user.username} -> {membership.role}")

        self.stdout.write(
            self.style.SUCCESS(
                "seed_local_users done "
                f"tenant_created={tenant_created} "
                f"created_users={created_users} updated_users={updated_users} "
                f"created_memberships={created_memberships} updated_memberships={updated_memberships}"
            )
        )

        self.stdout.write("Local credentials (development only):")
        for config in ROLE_USERS:
            self.stdout.write(
                f"- {config['username']} / {password} / role={config['role']} ({config['description']})"
            )
