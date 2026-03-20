import uuid

from django.db import models
from django.contrib.auth import get_user_model


User = get_user_model()


class PatientCaseSession(models.Model):
	"""
	HIPAA-compliant audit log for patient case analysis sessions.

	IMPORTANT: This model stores NO protected health information (PHI).
	Only metadata required for the audit trail is persisted here.
	Original patient text, de-identified text, and analysis output are
	never written to the database.
	"""

	session_id = models.UUIDField(
		primary_key=True,
		default=uuid.uuid4,
		editable=False,
		help_text="Unique session ID returned to the requesting client.",
	)
	created_at = models.DateTimeField(auto_now_add=True)
	domain = models.CharField(max_length=64, blank=True, default="medical")
	subdomain = models.CharField(max_length=128, blank=True, default="")
	# One-way SHA-256 hash of the original text — used for dedup only, no PHI recoverable.
	text_hash = models.CharField(max_length=64, blank=True, default="")
	# Audit counters — which PHI categories were present (not the values themselves).
	redaction_count = models.IntegerField(default=0)
	redaction_categories = models.JSONField(
		default=dict,
		help_text='E.g. {"DATE": 3, "PHONE_FAX": 1}',
	)
	# Non-PHI source metadata.
	source_filename = models.CharField(max_length=255, blank=True, default="")
	user_id = models.CharField(max_length=128, blank=True, default="anonymous")

	class Meta:
		ordering = ["-created_at"]
		verbose_name = "Patient Case Session"
		verbose_name_plural = "Patient Case Sessions"

	def __str__(self) -> str:
		return f"PatientCaseSession({self.session_id}, {self.created_at:%Y-%m-%d})"


class SecurityEvent(models.Model):
	"""Security and abuse telemetry for incident response and threat analysis."""

	class Severity(models.TextChoices):
		LOW = "low", "Low"
		MEDIUM = "medium", "Medium"
		HIGH = "high", "High"
		CRITICAL = "critical", "Critical"

	event_type = models.CharField(max_length=64)
	severity = models.CharField(max_length=16, choices=Severity.choices, default=Severity.MEDIUM)
	ip_address = models.GenericIPAddressField(null=True, blank=True)
	path = models.CharField(max_length=255, blank=True, default="")
	method = models.CharField(max_length=12, blank=True, default="")
	user_agent = models.CharField(max_length=512, blank=True, default="")
	user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="security_events")
	meta = models.JSONField(default=dict)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-created_at"]
		indexes = [
			models.Index(fields=["event_type", "created_at"]),
			models.Index(fields=["severity", "created_at"]),
			models.Index(fields=["ip_address", "created_at"]),
		]

	def __str__(self) -> str:
		return f"SecurityEvent({self.event_type}, {self.severity}, {self.created_at:%Y-%m-%d %H:%M:%S})"


class Tenant(models.Model):
	"""SaaS tenant entity representing an organization or individual account."""

	class Type(models.TextChoices):
		INDIVIDUAL = "individual", "Individual"
		CLINIC = "clinic", "Clinic"
		HOSPITAL = "hospital", "Hospital"
		INSTITUTION = "institution", "Institution"

	tenant_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
	name = models.CharField(max_length=200)
	tenant_type = models.CharField(max_length=24, choices=Type.choices, default=Type.INDIVIDUAL)
	owner = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="owned_tenants")
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)
	is_active = models.BooleanField(default=True)

	class Meta:
		ordering = ["-created_at"]

	def __str__(self) -> str:
		return f"Tenant({self.name}, {self.tenant_type})"


class TenantMembership(models.Model):
	"""Maps users to tenants with RBAC role assignments."""

	class Role(models.TextChoices):
		OWNER = "owner", "Owner"
		ADMIN = "admin", "Admin"
		CLINICIAN = "clinician", "Clinician"
		AUDITOR = "auditor", "Auditor"

	tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="memberships")
	user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tenant_memberships")
	role = models.CharField(max_length=16, choices=Role.choices, default=Role.CLINICIAN)
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["tenant__name", "user__username"]
		constraints = [
			models.UniqueConstraint(fields=["tenant", "user"], name="unique_tenant_user_membership"),
		]
		indexes = [
			models.Index(fields=["tenant", "role"]),
			models.Index(fields=["user", "is_active"]),
		]

	def __str__(self) -> str:
		return f"TenantMembership({self.tenant.name}, {self.user_id}, {self.role})"


class SubscriptionPlan(models.Model):
	"""Catalog of subscription plans for monthly/annual billing."""

	class BillingCycle(models.TextChoices):
		MONTHLY = "monthly", "Monthly"
		ANNUAL = "annual", "Annual"

	code = models.CharField(max_length=64, unique=True)
	name = models.CharField(max_length=128)
	description = models.TextField(blank=True, default="")
	billing_cycle = models.CharField(max_length=16, choices=BillingCycle.choices)
	price_cents = models.PositiveIntegerField()
	billing_model = models.CharField(max_length=24, default="hybrid")
	currency = models.CharField(max_length=8, default="USD")
	provider = models.CharField(max_length=32, default="stripe")
	provider_price_id = models.CharField(max_length=128, blank=True, default="")
	provider_product_id = models.CharField(max_length=128, blank=True, default="")
	trial_days_default = models.PositiveIntegerField(default=30)
	max_monthly_requests = models.PositiveIntegerField(default=10000)
	max_users = models.PositiveIntegerField(default=5)
	seat_price_cents = models.PositiveIntegerField(default=0)
	api_overage_per_1000_cents = models.PositiveIntegerField(default=0)
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["price_cents", "name"]

	def __str__(self) -> str:
		return f"Plan({self.code}, {self.billing_cycle}, {self.price_cents} {self.currency})"


class Subscription(models.Model):
	"""Tenant subscription state; payment provider integration can sync this model."""

	class Status(models.TextChoices):
		TRIALING = "trialing", "Trialing"
		ACTIVE = "active", "Active"
		PAST_DUE = "past_due", "Past Due"
		CANCELED = "canceled", "Canceled"
		INCOMPLETE = "incomplete", "Incomplete"

	tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="subscriptions")
	plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name="subscriptions")
	status = models.CharField(max_length=16, choices=Status.choices, default=Status.TRIALING)
	provider = models.CharField(max_length=32, default="internal")
	provider_customer_id = models.CharField(max_length=128, blank=True, default="")
	provider_subscription_id = models.CharField(max_length=128, blank=True, default="")
	trial_ends_at = models.DateTimeField(null=True, blank=True)
	current_period_start = models.DateTimeField(null=True, blank=True)
	current_period_end = models.DateTimeField(null=True, blank=True)
	canceled_at = models.DateTimeField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-created_at"]
		indexes = [
			models.Index(fields=["status", "current_period_end"]),
		]

	def __str__(self) -> str:
		return f"Subscription({self.tenant.tenant_id}, {self.plan.code}, {self.status})"


class UsageRecord(models.Model):
	"""Aggregated usage events used for quota management and billing analytics."""

	tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="usage_records")
	metric = models.CharField(max_length=64)
	quantity = models.PositiveIntegerField(default=1)
	timestamp = models.DateTimeField(auto_now_add=True)
	meta = models.JSONField(default=dict)

	class Meta:
		ordering = ["-timestamp"]
		indexes = [
			models.Index(fields=["tenant", "metric", "timestamp"]),
		]

	def __str__(self) -> str:
		return f"UsageRecord({self.tenant.tenant_id}, {self.metric}, {self.quantity})"


class BillingEvent(models.Model):
	"""Incoming/outgoing billing lifecycle events (webhooks, checkout intents, etc.)."""

	event_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
	tenant = models.ForeignKey(Tenant, null=True, blank=True, on_delete=models.SET_NULL, related_name="billing_events")
	event_type = models.CharField(max_length=64)
	provider = models.CharField(max_length=32, default="internal")
	provider_event_id = models.CharField(max_length=128, blank=True, default="")
	status = models.CharField(max_length=32, blank=True, default="received")
	payload = models.JSONField(default=dict)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-created_at"]
		indexes = [
			models.Index(fields=["provider", "provider_event_id"]),
			models.Index(fields=["event_type", "created_at"]),
		]

	def __str__(self) -> str:
		return f"BillingEvent({self.event_type}, {self.provider}, {self.created_at:%Y-%m-%d})"


class BillingInvoice(models.Model):
	"""Periodic invoice snapshot generated from hybrid billing components."""

	class Status(models.TextChoices):
		DRAFT = "draft", "Draft"
		FINALIZED = "finalized", "Finalized"
		PAID = "paid", "Paid"
		VOID = "void", "Void"

	invoice_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
	tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="billing_invoices")
	subscription = models.ForeignKey(Subscription, null=True, blank=True, on_delete=models.SET_NULL, related_name="billing_invoices")
	period_start = models.DateTimeField()
	period_end = models.DateTimeField()
	currency = models.CharField(max_length=8, default="USD")
	status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
	platform_fee_cents = models.PositiveIntegerField(default=0)
	users_overage_cents = models.PositiveIntegerField(default=0)
	api_overage_cents = models.PositiveIntegerField(default=0)
	total_cents = models.PositiveIntegerField(default=0)
	active_users = models.PositiveIntegerField(default=0)
	api_requests = models.PositiveIntegerField(default=0)
	overage_users = models.PositiveIntegerField(default=0)
	overage_api_requests = models.PositiveIntegerField(default=0)
	external_invoice_id = models.CharField(max_length=128, blank=True, default="")
	meta = models.JSONField(default=dict)
	generated_at = models.DateTimeField(auto_now_add=True)
	paid_at = models.DateTimeField(null=True, blank=True)

	class Meta:
		ordering = ["-generated_at"]
		constraints = [
			models.UniqueConstraint(fields=["tenant", "period_start", "period_end"], name="unique_tenant_period_invoice"),
		]
		indexes = [
			models.Index(fields=["tenant", "status", "generated_at"]),
		]

	def __str__(self) -> str:
		return f"BillingInvoice({self.tenant_id}, {self.period_start:%Y-%m}, {self.total_cents})"


class BillingInvoiceLineItem(models.Model):
	"""Normalized invoice lines for platform fee and overage components."""

	invoice = models.ForeignKey(BillingInvoice, on_delete=models.CASCADE, related_name="line_items")
	code = models.CharField(max_length=64)
	description = models.CharField(max_length=255)
	quantity = models.PositiveIntegerField(default=1)
	unit_price_cents = models.PositiveIntegerField(default=0)
	total_price_cents = models.PositiveIntegerField(default=0)
	meta = models.JSONField(default=dict)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["id"]
		indexes = [
			models.Index(fields=["invoice", "code"]),
		]

	def __str__(self) -> str:
		return f"BillingInvoiceLineItem({self.invoice_id}, {self.code}, {self.total_price_cents})"
