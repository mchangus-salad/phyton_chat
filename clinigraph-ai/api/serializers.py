import os

from rest_framework import serializers


class ConversationTurnSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=["user", "assistant"], default="user")
    content = serializers.CharField(max_length=4000, allow_blank=False, trim_whitespace=True)


class AgentQuerySerializer(serializers.Serializer):
    question = serializers.CharField(max_length=2000, allow_blank=False, trim_whitespace=True)
    user_id = serializers.CharField(max_length=128, required=False, default="anonymous")
    conversation_history = ConversationTurnSerializer(many=True, required=False, default=list)


class HealthResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    framework = serializers.CharField()


class AgentQueryResponseSerializer(serializers.Serializer):
    answer = serializers.CharField()
    cache_hit = serializers.BooleanField()
    request_id = serializers.CharField()


class AgentChatSessionCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255, required=False, allow_blank=True, trim_whitespace=True)


class AgentChatMessageCreateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=["user", "assistant"])
    content = serializers.CharField(max_length=12000, allow_blank=False, trim_whitespace=True)
    request_id = serializers.CharField(max_length=128, required=False, allow_blank=True, trim_whitespace=True)


class AgentChatHighlightCreateSerializer(serializers.Serializer):
    message_id = serializers.IntegerField(min_value=1)
    selected_text = serializers.CharField(max_length=4000, allow_blank=False, trim_whitespace=True)
    start_offset = serializers.IntegerField(min_value=0)
    end_offset = serializers.IntegerField(min_value=1)
    context_snippet = serializers.CharField(max_length=280, required=False, allow_blank=True, trim_whitespace=True)

    def validate(self, attrs):
        if attrs["end_offset"] <= attrs["start_offset"]:
            raise serializers.ValidationError("end_offset must be greater than start_offset")
        return attrs


class AgentChatHighlightSerializer(serializers.Serializer):
    highlight_id = serializers.IntegerField()
    message_id = serializers.IntegerField()
    selected_text = serializers.CharField()
    start_offset = serializers.IntegerField()
    end_offset = serializers.IntegerField()
    context_snippet = serializers.CharField(required=False, allow_blank=True)
    created_at = serializers.DateTimeField()


class AgentChatMessageSerializer(serializers.Serializer):
    message_id = serializers.IntegerField()
    role = serializers.CharField()
    content = serializers.CharField()
    request_id = serializers.CharField(required=False, allow_blank=True)
    created_at = serializers.DateTimeField()


class AgentChatSessionSummarySerializer(serializers.Serializer):
    session_id = serializers.UUIDField()
    title = serializers.CharField()
    updated_at = serializers.DateTimeField()
    last_activity_at = serializers.DateTimeField()
    preview = serializers.CharField(required=False, allow_blank=True)
    highlights_preview = AgentChatHighlightSerializer(many=True, required=False)


class AgentChatPaginationSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    limit = serializers.IntegerField()
    offset = serializers.IntegerField()
    has_more = serializers.BooleanField()


class AgentChatSessionListResponseSerializer(serializers.Serializer):
    items = AgentChatSessionSummarySerializer(many=True)
    pagination = AgentChatPaginationSerializer()


class AgentChatSessionDetailSerializer(serializers.Serializer):
    session_id = serializers.UUIDField()
    title = serializers.CharField()
    updated_at = serializers.DateTimeField()
    last_activity_at = serializers.DateTimeField()
    messages = AgentChatMessageSerializer(many=True)
    messages_pagination = AgentChatPaginationSerializer(required=False)
    highlights = AgentChatHighlightSerializer(many=True)


class DomainQueryResponseSerializer(AgentQueryResponseSerializer):
    domain = serializers.CharField()
    subdomain = serializers.CharField(required=False, allow_blank=True)
    safety_notice = serializers.CharField()
    citations = serializers.ListField(child=serializers.CharField(), required=False, default=list)


class KnowledgeDocumentSerializer(serializers.Serializer):
    source = serializers.CharField(max_length=255, allow_blank=False, trim_whitespace=True)
    title = serializers.CharField(max_length=255, required=False, allow_blank=True, trim_whitespace=True)
    text = serializers.CharField(max_length=12000, allow_blank=False, trim_whitespace=True)
    subdomain = serializers.CharField(max_length=128, required=False, allow_blank=True, trim_whitespace=True)
    condition = serializers.CharField(max_length=128, required=False, allow_blank=True, trim_whitespace=True)
    markers = serializers.ListField(
        child=serializers.CharField(max_length=128, trim_whitespace=True),
        required=False,
        allow_empty=True,
    )
    cancer_type = serializers.CharField(max_length=128, required=False, allow_blank=True, trim_whitespace=True)
    biomarkers = serializers.ListField(
        child=serializers.CharField(max_length=128, trim_whitespace=True),
        required=False,
        allow_empty=True,
    )
    evidence_type = serializers.CharField(max_length=128, required=False, allow_blank=True, trim_whitespace=True)
    publication_year = serializers.IntegerField(required=False, min_value=1800, max_value=2100)
    created_at = serializers.DateTimeField(required=False)


class OncologyTrainingSerializer(serializers.Serializer):
    corpus_name = serializers.CharField(max_length=128, required=False, default="oncology-research")
    subdomain = serializers.CharField(max_length=128, required=False, allow_blank=True, trim_whitespace=True)
    dedup_mode = serializers.ChoiceField(required=False, default="upsert", choices=["upsert", "batch-dedup", "versioned"])
    version_tag = serializers.CharField(max_length=64, required=False, allow_blank=True, trim_whitespace=True)
    documents = KnowledgeDocumentSerializer(many=True, allow_empty=False)


class MedicalTrainingSerializer(OncologyTrainingSerializer):
    corpus_name = serializers.CharField(max_length=128, required=False, default="medical-research")
    domain = serializers.CharField(max_length=128, required=False, allow_blank=True, trim_whitespace=True)


class OncologyTrainingResponseSerializer(serializers.Serializer):
    domain = serializers.CharField()
    subdomain = serializers.CharField(required=False, allow_blank=True)
    corpus_name = serializers.CharField()
    documents_received = serializers.IntegerField()
    duplicates_dropped = serializers.IntegerField(required=False)
    documents_indexed = serializers.IntegerField()
    dedup_mode = serializers.CharField(required=False)
    version_tag = serializers.CharField(required=False, allow_blank=True)
    request_id = serializers.CharField()


class MedicalTrainingResponseSerializer(OncologyTrainingResponseSerializer):
    pass


class OncologyQuerySerializer(AgentQuerySerializer):
    subdomain = serializers.CharField(max_length=128, required=False, allow_blank=True, trim_whitespace=True)


class MedicalQuerySerializer(OncologyQuerySerializer):
    domain = serializers.CharField(max_length=128, required=False, allow_blank=True, trim_whitespace=True)


class OncologyFileUploadSerializer(serializers.Serializer):
    corpus_name = serializers.CharField(max_length=128, required=False, default="oncology-upload")
    subdomain = serializers.CharField(max_length=128, required=False, allow_blank=True, trim_whitespace=True)
    file = serializers.FileField()


class MedicalFileUploadSerializer(OncologyFileUploadSerializer):
    corpus_name = serializers.CharField(max_length=128, required=False, default="medical-upload")
    domain = serializers.CharField(max_length=128, required=False, allow_blank=True, trim_whitespace=True)


class OncologyEvidenceSearchSerializer(serializers.Serializer):
    query = serializers.CharField(max_length=2000, allow_blank=False, trim_whitespace=True)
    domain = serializers.CharField(max_length=128, required=False, allow_blank=True, trim_whitespace=True)
    subdomain = serializers.CharField(max_length=128, required=False, allow_blank=True, trim_whitespace=True)
    condition = serializers.CharField(max_length=128, required=False, allow_blank=True, trim_whitespace=True)
    marker = serializers.CharField(max_length=128, required=False, allow_blank=True, trim_whitespace=True)
    cancer_type = serializers.CharField(max_length=128, required=False, allow_blank=True, trim_whitespace=True)
    biomarker = serializers.CharField(max_length=128, required=False, allow_blank=True, trim_whitespace=True)
    evidence_type = serializers.CharField(max_length=128, required=False, allow_blank=True, trim_whitespace=True)
    publication_year_from = serializers.IntegerField(required=False, min_value=1800, max_value=2100)
    publication_year_to = serializers.IntegerField(required=False, min_value=1800, max_value=2100)
    rerank = serializers.BooleanField(required=False, default=True)
    max_results = serializers.IntegerField(required=False, min_value=1, max_value=20, default=5)


class MedicalEvidenceSearchSerializer(OncologyEvidenceSearchSerializer):
    pass


class EvidenceDocumentSerializer(serializers.Serializer):
    citation_id = serializers.CharField()
    citation_label = serializers.CharField()
    source = serializers.CharField()
    title = serializers.CharField(required=False, allow_blank=True)
    text = serializers.CharField()
    subdomain = serializers.CharField(required=False, allow_blank=True)
    condition = serializers.CharField(required=False, allow_blank=True)
    markers = serializers.ListField(child=serializers.CharField(), required=False)
    cancer_type = serializers.CharField(required=False, allow_blank=True)
    biomarkers = serializers.ListField(child=serializers.CharField(), required=False)
    evidence_type = serializers.CharField(required=False, allow_blank=True)
    publication_year = serializers.IntegerField(required=False)
    score = serializers.FloatField(required=False)
    rerank_score = serializers.FloatField(required=False)


class OncologyEvidenceSearchResponseSerializer(serializers.Serializer):
    domain = serializers.CharField()
    subdomain = serializers.CharField(required=False, allow_blank=True)
    query = serializers.CharField()
    evidence = EvidenceDocumentSerializer(many=True)
    request_id = serializers.CharField()
    safety_notice = serializers.CharField()


class MedicalEvidenceSearchResponseSerializer(OncologyEvidenceSearchResponseSerializer):
    pass


class ErrorResponseSerializer(serializers.Serializer):
    error = serializers.CharField()
    request_id = serializers.CharField(required=False)
    detail = serializers.JSONField(required=False)


class MetricsResponseSerializer(serializers.Serializer):
    metrics = serializers.DictField(child=serializers.FloatField())
    generated_at = serializers.DateTimeField()


class SecurityEventSerializer(serializers.Serializer):
    event_type = serializers.CharField()
    severity = serializers.CharField()
    ip_address = serializers.CharField(required=False, allow_blank=True)
    path = serializers.CharField(required=False, allow_blank=True)
    method = serializers.CharField(required=False, allow_blank=True)
    user_agent = serializers.CharField(required=False, allow_blank=True)
    meta = serializers.JSONField(required=False)
    created_at = serializers.DateTimeField()


class SubscriptionPlanSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True)
    billing_cycle = serializers.CharField()
    billing_model = serializers.CharField(required=False)
    price_cents = serializers.IntegerField()
    currency = serializers.CharField()
    provider = serializers.CharField(required=False)
    provider_price_id = serializers.CharField(required=False, allow_blank=True)
    trial_days_default = serializers.IntegerField()
    max_monthly_requests = serializers.IntegerField()
    max_users = serializers.IntegerField()
    seat_price_cents = serializers.IntegerField(required=False)
    api_overage_per_1000_cents = serializers.IntegerField(required=False)


class SubscriptionCreateSerializer(serializers.Serializer):
    tenant_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    tenant_type = serializers.ChoiceField(
        choices=["individual", "clinic", "hospital", "institution"],
        required=False,
        default="individual",
    )
    plan_code = serializers.CharField(max_length=64)
    trial_days = serializers.IntegerField(required=False, min_value=0, max_value=60)


class SubscriptionCreateResponseSerializer(serializers.Serializer):
    tenant_id = serializers.UUIDField()
    subscription_id = serializers.IntegerField()
    status = serializers.CharField()
    trial_ends_at = serializers.DateTimeField(required=False, allow_null=True)
    checkout_hint = serializers.CharField()


class CheckoutSessionCreateSerializer(serializers.Serializer):
    tenant_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    tenant_type = serializers.ChoiceField(
        choices=["individual", "clinic", "hospital", "institution"],
        required=False,
        default="individual",
    )
    plan_code = serializers.CharField(max_length=64)


class CheckoutSessionResponseSerializer(serializers.Serializer):
    tenant_id = serializers.UUIDField()
    subscription_id = serializers.IntegerField()
    provider = serializers.CharField()
    checkout_url = serializers.CharField()
    checkout_session_id = serializers.CharField()


class UsageIngestSerializer(serializers.Serializer):
    tenant_id = serializers.UUIDField()
    metric = serializers.CharField(max_length=64)
    quantity = serializers.IntegerField(min_value=1, default=1)
    meta = serializers.JSONField(required=False, default=dict)


class BillingWebhookSerializer(serializers.Serializer):
    provider = serializers.CharField(max_length=32)
    event_type = serializers.CharField(max_length=64)
    provider_event_id = serializers.CharField(max_length=128, required=False, allow_blank=True)
    tenant_id = serializers.UUIDField(required=False)
    payload = serializers.JSONField(required=False, default=dict)


class TenantMemberSerializer(serializers.Serializer):
    membership_id = serializers.IntegerField()
    tenant_id = serializers.UUIDField()
    user_id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.EmailField(required=False, allow_blank=True)
    role = serializers.CharField()
    is_active = serializers.BooleanField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class TenantMembershipCreateSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150, required=False, allow_blank=True, trim_whitespace=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    password = serializers.CharField(max_length=128, required=False, allow_blank=True, write_only=True)
    role = serializers.ChoiceField(
        choices=[
            "owner",
            "admin",
            "billing",
            "clinician",
            "auditor",
        ],
        default="clinician",
    )

    def validate(self, attrs):
        username = (attrs.get("username") or "").strip()
        email = (attrs.get("email") or "").strip()
        if not username and not email:
            raise serializers.ValidationError("Provide either username or email.")
        return attrs


class TenantMembershipUpdateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(
        choices=[
            "owner",
            "admin",
            "billing",
            "clinician",
            "auditor",
        ],
        required=False,
    )
    is_active = serializers.BooleanField(required=False)


class BillingEstimateSerializer(serializers.Serializer):
    active_users = serializers.IntegerField(required=False, min_value=0)
    api_requests = serializers.IntegerField(required=False, min_value=0)


class BillingEstimateResponseSerializer(serializers.Serializer):
    tenant_id = serializers.UUIDField()
    plan_code = serializers.CharField()
    currency = serializers.CharField()
    billing_cycle = serializers.CharField()
    period_start = serializers.DateTimeField()
    period_end = serializers.DateTimeField()
    included_users = serializers.IntegerField()
    included_api_requests = serializers.IntegerField()
    active_users = serializers.IntegerField()
    api_requests = serializers.IntegerField()
    overage_users = serializers.IntegerField()
    overage_api_requests = serializers.IntegerField()
    platform_fee_cents = serializers.IntegerField()
    users_overage_cents = serializers.IntegerField()
    api_overage_cents = serializers.IntegerField()
    total_cents = serializers.IntegerField()


class TaxInfoUpdateSerializer(serializers.Serializer):
    """Request body for PATCH /billing/tax-info/."""

    tax_id = serializers.CharField(
        max_length=64,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        help_text="VAT registration number or EIN.",
    )
    tax_country_code = serializers.CharField(
        max_length=2,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        help_text="ISO 3166-1 alpha-2 billing country (e.g. 'DE', 'US').",
    )
    tax_region_code = serializers.CharField(
        max_length=16,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        help_text="Sub-national region code for finer-grained tax lookup (e.g. 'TX', 'CA').",
    )
    tax_exempt = serializers.BooleanField(
        required=False,
        help_text="Set to true to mark this tenant as tax-exempt.",
    )

    def validate_tax_country_code(self, value: str) -> str:
        return value.upper()

    def validate_tax_region_code(self, value: str) -> str:
        return value.upper()


class TaxInfoResponseSerializer(serializers.Serializer):
    tenant_id = serializers.UUIDField()
    tax_id = serializers.CharField()
    tax_country_code = serializers.CharField()
    tax_region_code = serializers.CharField()
    tax_exempt = serializers.BooleanField()


class BillingInvoiceCloseSerializer(serializers.Serializer):
    active_users = serializers.IntegerField(required=False, min_value=0)
    api_requests = serializers.IntegerField(required=False, min_value=0)


class BillingInvoiceSerializer(serializers.Serializer):
    invoice_id = serializers.UUIDField()
    tenant_id = serializers.UUIDField()
    subscription_id = serializers.IntegerField(required=False, allow_null=True)
    period_start = serializers.DateTimeField()
    period_end = serializers.DateTimeField()
    currency = serializers.CharField()
    status = serializers.CharField()
    platform_fee_cents = serializers.IntegerField()
    users_overage_cents = serializers.IntegerField()
    api_overage_cents = serializers.IntegerField()
    tax_cents = serializers.IntegerField()
    tax_rate_bps = serializers.IntegerField()
    total_cents = serializers.IntegerField()
    active_users = serializers.IntegerField()
    api_requests = serializers.IntegerField()
    overage_users = serializers.IntegerField()
    overage_api_requests = serializers.IntegerField()
    generated_at = serializers.DateTimeField()


class BillingInvoiceLineItemSerializer(serializers.Serializer):
    code = serializers.CharField()
    description = serializers.CharField()
    quantity = serializers.IntegerField()
    unit_price_cents = serializers.IntegerField()
    total_price_cents = serializers.IntegerField()
    meta = serializers.JSONField(required=False)


class BillingInvoiceDetailSerializer(BillingInvoiceSerializer):
    meta = serializers.JSONField(required=False)
    line_items = BillingInvoiceLineItemSerializer(many=True)


class BillingUsageSummaryResponseSerializer(serializers.Serializer):
    tenant_id = serializers.UUIDField()
    period_start = serializers.DateTimeField()
    period_end = serializers.DateTimeField()
    active_users = serializers.IntegerField()
    api_requests = serializers.IntegerField()
    included_users = serializers.IntegerField()
    included_api_requests = serializers.IntegerField()
    overage_users = serializers.IntegerField()
    overage_api_requests = serializers.IntegerField()
    subscription_status = serializers.CharField()
    entitlement_allowed = serializers.BooleanField()
    grace_period_ends_at = serializers.DateTimeField(required=False, allow_null=True)
    latest_invoice = BillingInvoiceSerializer(required=False, allow_null=True)


class BillingPortalSessionSerializer(serializers.Serializer):
    return_url = serializers.CharField(required=False, allow_blank=True)


class BillingPortalSessionResponseSerializer(serializers.Serializer):
    portal_url = serializers.CharField()
    session_id = serializers.CharField()


class SubscriptionPlanChangeSerializer(serializers.Serializer):
    target_plan_code = serializers.CharField(max_length=64)
    apply = serializers.BooleanField(required=False, default=False)


class SubscriptionPlanChangeResponseSerializer(serializers.Serializer):
    subscription_id = serializers.IntegerField()
    previous_plan_code = serializers.CharField()
    target_plan_code = serializers.CharField()
    applied = serializers.BooleanField()
    proration_preview = serializers.DictField()


class SubscriptionCancelSerializer(serializers.Serializer):
    immediately = serializers.BooleanField(
        required=False,
        default=False,
        help_text=(
            "If true, cancel immediately and revoke access now. "
            "If false (default), cancel at the end of the current billing period."
        ),
    )


class SubscriptionCancelResponseSerializer(serializers.Serializer):
    subscription_id = serializers.IntegerField()
    status = serializers.CharField()
    canceled_at = serializers.DateTimeField(allow_null=True)
    cancel_at_period_end = serializers.BooleanField()


class PatientCaseUploadSerializer(serializers.Serializer):
    """
    Input for the patient case analysis endpoint.

    Either ``text`` (free-text clinical note) or ``file`` (document upload)
    must be provided.  Both may be supplied simultaneously — the file takes
    precedence when both are present.
    """

    text = serializers.CharField(
        max_length=100_000,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        help_text=(
            "Free-text patient case: history, symptoms, lab results, medications, etc. "
            "All PHI is automatically redacted before processing."
        ),
    )
    file = serializers.FileField(
        required=False,
        help_text="Patient document file (.txt, .pdf, .docx, .csv, .json). Max 10 MB.",
    )
    domain = serializers.CharField(
        max_length=64,
        required=False,
        default="medical",
        trim_whitespace=True,
        help_text="Medical domain for evidence retrieval (e.g. 'cardiology', 'neurology').",
    )
    subdomain = serializers.CharField(
        max_length=128,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        help_text="Optional subdomain filter (e.g. 'heart-failure', 'arrhythmia').",
    )
    question = serializers.CharField(
        max_length=2000,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        help_text="Optional specific clinical question to answer about this case.",
    )
    user_id = serializers.CharField(
        max_length=128,
        required=False,
        default="anonymous",
        trim_whitespace=True,
    )

    def validate_file(self, value):
        allowed = frozenset({".txt", ".pdf", ".docx", ".csv", ".json"})
        ext = os.path.splitext(value.name)[1].lower()
        if ext not in allowed:
            raise serializers.ValidationError(
                f"File type '{ext}' is not supported. "
                f"Accepted types: {', '.join(sorted(allowed))}"
            )
        max_bytes = 10 * 1024 * 1024  # 10 MB
        if value.size > max_bytes:
            raise serializers.ValidationError("File must not exceed 10 MB.")
        return value

    def validate(self, data):
        if not data.get("text") and not data.get("file"):
            raise serializers.ValidationError(
                "Provide either 'text' (clinical note) or 'file' (document upload)."
            )
        return data


class PatientCaseAnalysisResponseSerializer(serializers.Serializer):
    """Response returned by the patient case analysis endpoint."""

    session_id = serializers.UUIDField(
        help_text="Unique ID for this analysis session — use for audit trail queries.",
    )
    analysis = serializers.CharField(
        help_text="Evidence-based clinical recommendations and findings.",
    )
    citations = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
        help_text="Reference studies and guidelines used in the analysis.",
    )
    redaction_summary = serializers.DictField(
        help_text=(
            "Audit summary of PHI categories detected and redacted from the document. "
            'E.g. {"total_redactions": 4, "categories": {"DATE": 3, "PHONE_FAX": 1}}'
        ),
    )
    domain = serializers.CharField()
    safety_notice = serializers.CharField()
    request_id = serializers.CharField()


class AsyncIngestionAcceptedSerializer(serializers.Serializer):
    """202 Accepted response for fire-and-forget corpus ingestion jobs."""

    job_id = serializers.UUIDField(
        help_text='Track this job via GET /api/v1/jobs/{job_id}/',
    )
    status = serializers.CharField(default='pending')
    status_url = serializers.CharField(
        help_text='Poll this URL to observe job progress.',
    )
    domain = serializers.CharField(required=False, allow_blank=True)
    corpus_name = serializers.CharField(required=False, allow_blank=True)


class IngestionJobSerializer(serializers.Serializer):
    """Full status response for a corpus ingestion job."""

    job_id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=['pending', 'running', 'completed', 'failed'])
    domain = serializers.CharField(required=False, allow_blank=True)
    subdomain = serializers.CharField(required=False, allow_blank=True)
    corpus_name = serializers.CharField(required=False, allow_blank=True)
    result = serializers.JSONField(required=False, allow_null=True)
    error = serializers.CharField(required=False, allow_blank=True)
    submitted_by = serializers.CharField(required=False)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


# ── Mobile API serializers ────────────────────────────────────────────────────

class DeviceTokenRegisterSerializer(serializers.Serializer):
    """Register or refresh a push notification device token."""

    token = serializers.CharField(
        max_length=512,
        help_text="FCM registration token or APNs device token.",
    )
    platform = serializers.ChoiceField(choices=['fcm', 'apns'])
    device_label = serializers.CharField(max_length=128, required=False, allow_blank=True, default='')
    app_version = serializers.CharField(max_length=32, required=False, allow_blank=True, default='')


class DeviceTokenResponseSerializer(serializers.Serializer):
    """Response payload after registering a device token."""

    device_id = serializers.UUIDField()
    platform = serializers.CharField()
    device_label = serializers.CharField()
    is_active = serializers.BooleanField()
    registered_at = serializers.DateTimeField()


class MobileCaseUploadSerializer(serializers.Serializer):
    """Mobile patient-case upload: file + optional metadata."""

    file = serializers.FileField(
        help_text="Patient case document (PDF, TXT, or plain text).",
    )
    domain = serializers.CharField(
        max_length=64,
        required=False,
        default='medical',
        help_text="Clinical domain (e.g. 'oncology', 'cardiology').",
    )
    subdomain = serializers.CharField(max_length=128, required=False, allow_blank=True, default='')
    note = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
        default='',
        help_text="Optional clinician note attached to this upload.",
    )


class MobileCaseUploadResponseSerializer(serializers.Serializer):
    """Response after a successful mobile case upload."""

    session_id = serializers.UUIDField()
    domain = serializers.CharField()
    redaction_count = serializers.IntegerField(
        help_text="Number of PHI entities redacted from the uploaded document.",
    )
    redaction_categories = serializers.JSONField(
        help_text='e.g. {"DATE": 2, "PHONE_FAX": 1}',
    )
    source_filename = serializers.CharField()
    created_at = serializers.DateTimeField()


class MobileEvidenceQuerySerializer(serializers.Serializer):
    """Mobile evidence search request."""

    query = serializers.CharField(max_length=1000, allow_blank=False, trim_whitespace=True)
    domain = serializers.CharField(max_length=64, required=False, default='medical')
    top_k = serializers.IntegerField(min_value=1, max_value=20, required=False, default=5)


class MobileEvidenceResultSerializer(serializers.Serializer):
    """Single evidence item returned for the mobile evidence viewer."""

    rank = serializers.IntegerField()
    title = serializers.CharField(allow_blank=True)
    excerpt = serializers.CharField()
    source = serializers.CharField(allow_blank=True)
    score = serializers.FloatField(required=False, allow_null=True)


class MobileEvidenceResponseSerializer(serializers.Serializer):
    """Response for the mobile evidence viewer endpoint."""

    results = MobileEvidenceResultSerializer(many=True)
    query = serializers.CharField()
    domain = serializers.CharField()
    total = serializers.IntegerField()
