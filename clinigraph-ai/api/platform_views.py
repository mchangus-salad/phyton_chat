import secrets
import csv
import io
from datetime import timedelta

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import BillingEvent, BillingInvoice, BillingInvoiceLineItem, SecurityEvent, Subscription, SubscriptionPlan, Tenant, TenantMembership, UsageRecord
from .billing import BillingConfigurationError, StripeBillingProvider
from .invoice_render import render_invoice_pdf
from .permissions import HasAgentApiKeyOrAuthenticated
from .permissions import IsTenantAdminOrOwner
from .services.platform_service import (
    change_subscription_plan,
    close_current_billing_period,
    create_portal_session,
    create_checkout_session,
    create_subscription_draft,
    estimate_hybrid_monthly_bill,
    get_active_plan_or_none,
    get_latest_billable_subscription,
    list_active_plans,
)
from .serializers import (
    BillingEstimateResponseSerializer,
    BillingEstimateSerializer,
    BillingInvoiceCloseSerializer,
    BillingInvoiceDetailSerializer,
    BillingInvoiceSerializer,
    BillingInvoiceLineItemSerializer,
    BillingPortalSessionResponseSerializer,
    BillingPortalSessionSerializer,
    BillingUsageSummaryResponseSerializer,
    CheckoutSessionCreateSerializer,
    CheckoutSessionResponseSerializer,
    BillingWebhookSerializer,
    ErrorResponseSerializer,
    MetricsResponseSerializer,
    SecurityEventSerializer,
    SubscriptionCreateResponseSerializer,
    SubscriptionCreateSerializer,
    SubscriptionPlanChangeResponseSerializer,
    SubscriptionPlanChangeSerializer,
    SubscriptionPlanSerializer,
    UsageIngestSerializer,
)
from .telemetry import incr, prometheus_text, snapshot


def _request_id(request) -> str:
    return getattr(request, "request_id", "n/a")


def _serialize_invoice(invoice: BillingInvoice | None) -> dict | None:
    if invoice is None:
        return None
    return {
        "invoice_id": invoice.invoice_id,
        "tenant_id": invoice.tenant.tenant_id,
        "subscription_id": invoice.subscription_id,
        "period_start": invoice.period_start,
        "period_end": invoice.period_end,
        "currency": invoice.currency,
        "status": invoice.status,
        "platform_fee_cents": invoice.platform_fee_cents,
        "users_overage_cents": invoice.users_overage_cents,
        "api_overage_cents": invoice.api_overage_cents,
        "total_cents": invoice.total_cents,
        "active_users": invoice.active_users,
        "api_requests": invoice.api_requests,
        "overage_users": invoice.overage_users,
        "overage_api_requests": invoice.overage_api_requests,
        "generated_at": invoice.generated_at,
    }


def _serialize_invoice_detail(invoice: BillingInvoice | None) -> dict | None:
    base = _serialize_invoice(invoice)
    if base is None or invoice is None:
        return None
    line_items = list(BillingInvoiceLineItem.objects.filter(invoice=invoice).order_by("id"))
    base["meta"] = invoice.meta
    base["line_items"] = [
        {
            "code": item.code,
            "description": item.description,
            "quantity": item.quantity,
            "unit_price_cents": item.unit_price_cents,
            "total_price_cents": item.total_price_cents,
            "meta": item.meta,
        }
        for item in line_items
    ]
    return base


@extend_schema(
    operation_id="ops_metrics",
    description="Operational metrics for observability and abuse monitoring.",
    responses={200: MetricsResponseSerializer, 401: ErrorResponseSerializer, 403: ErrorResponseSerializer},
    parameters=[
        OpenApiParameter(
            name="X-API-Key",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.HEADER,
            required=False,
            description="API key alternative to JWT bearer authentication.",
        )
    ],
    auth=["BearerAuth", "ApiKeyAuth"],
)
@api_view(["GET"])
@permission_classes([HasAgentApiKeyOrAuthenticated])
def ops_metrics(request):
    return Response(
        {
            "metrics": {k: float(v) for k, v in snapshot().items()},
            "generated_at": timezone.now(),
        },
        status=status.HTTP_200_OK,
    )


@extend_schema(
    operation_id="ops_metrics_prometheus",
    description="Prometheus-compatible metrics exposition.",
    responses={200: OpenApiTypes.STR, 401: ErrorResponseSerializer, 403: ErrorResponseSerializer},
    parameters=[
        OpenApiParameter(
            name="X-API-Key",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.HEADER,
            required=False,
            description="API key alternative to JWT bearer authentication.",
        )
    ],
    auth=["BearerAuth", "ApiKeyAuth"],
)
@api_view(["GET"])
@permission_classes([HasAgentApiKeyOrAuthenticated])
def ops_metrics_prometheus(request):
    return HttpResponse(prometheus_text(), content_type="text/plain; version=0.0.4; charset=utf-8")


@extend_schema(
    operation_id="security_events_recent",
    description="Recent security events for SOC/SRE investigation.",
    responses={200: SecurityEventSerializer(many=True), 401: ErrorResponseSerializer, 403: ErrorResponseSerializer},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def security_events_recent(request):
    user = request.user
    if not user.is_staff:
        return Response({"error": "forbidden", "request_id": _request_id(request)}, status=status.HTTP_403_FORBIDDEN)

    limit = min(int(request.query_params.get("limit", 100)), 500)
    events = SecurityEvent.objects.all()[:limit]
    payload = [
        {
            "event_type": e.event_type,
            "severity": e.severity,
            "ip_address": str(e.ip_address or ""),
            "path": e.path,
            "method": e.method,
            "user_agent": e.user_agent,
            "meta": e.meta,
            "created_at": e.created_at,
        }
        for e in events
    ]
    return Response(payload, status=status.HTTP_200_OK)


@extend_schema(
    operation_id="subscription_plans",
    description="Public catalog of active SaaS subscription plans.",
    responses={200: SubscriptionPlanSerializer(many=True)},
    auth=[],
)
@api_view(["GET"])
def subscription_plans(request):
    plans = list_active_plans()
    data = [
        {
            "code": p.code,
            "name": p.name,
            "description": p.description,
            "billing_cycle": p.billing_cycle,
            "billing_model": p.billing_model,
            "price_cents": p.price_cents,
            "currency": p.currency,
            "provider": p.provider,
            "provider_price_id": p.provider_price_id,
            "trial_days_default": p.trial_days_default,
            "max_monthly_requests": p.max_monthly_requests,
            "max_users": p.max_users,
            "seat_price_cents": p.seat_price_cents,
            "api_overage_per_1000_cents": p.api_overage_per_1000_cents,
        }
        for p in plans
    ]
    return Response(data, status=status.HTTP_200_OK)


@extend_schema(
    operation_id="billing_estimate",
    description="Estimate monthly hybrid billing: base plan + active users overage + API usage overage.",
    request=BillingEstimateSerializer,
    responses={200: BillingEstimateResponseSerializer, 400: ErrorResponseSerializer, 401: ErrorResponseSerializer, 403: ErrorResponseSerializer},
    parameters=[
        OpenApiParameter(
            name="X-Tenant-ID",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.HEADER,
            required=True,
            description="Tenant UUID required for tenant-scoped estimate.",
        )
    ],
)
@api_view(["POST"])
@permission_classes([IsTenantAdminOrOwner])
def billing_estimate(request):
    serializer = BillingEstimateSerializer(data=request.data or {})
    if not serializer.is_valid():
        return Response({"error": "invalid payload", "detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    tenant = getattr(request, "tenant", None)
    if tenant is None:
        return Response({"error": "tenant not found", "request_id": _request_id(request)}, status=status.HTTP_400_BAD_REQUEST)

    subscription = get_latest_billable_subscription(tenant)
    if not subscription:
        return Response({"error": "active subscription not found", "request_id": _request_id(request)}, status=status.HTTP_400_BAD_REQUEST)

    payload = serializer.validated_data
    estimate = estimate_hybrid_monthly_bill(
        tenant=tenant,
        plan=subscription.plan,
        active_users=payload.get("active_users"),
        api_requests=payload.get("api_requests"),
    )

    return Response(
        {
            "tenant_id": estimate.tenant_id,
            "plan_code": estimate.plan_code,
            "currency": estimate.currency,
            "billing_cycle": estimate.billing_cycle,
            "period_start": estimate.period_start,
            "period_end": estimate.period_end,
            "included_users": estimate.included_users,
            "included_api_requests": estimate.included_api_requests,
            "active_users": estimate.active_users,
            "api_requests": estimate.api_requests,
            "overage_users": estimate.overage_users,
            "overage_api_requests": estimate.overage_api_requests,
            "platform_fee_cents": estimate.platform_fee_cents,
            "users_overage_cents": estimate.users_overage_cents,
            "api_overage_cents": estimate.api_overage_cents,
            "total_cents": estimate.total_cents,
        },
        status=status.HTTP_200_OK,
    )


@extend_schema(
    operation_id="billing_invoice_close",
    description="Close the current billing period and persist an invoice snapshot for the tenant.",
    request=BillingInvoiceCloseSerializer,
    responses={200: BillingInvoiceSerializer, 400: ErrorResponseSerializer, 401: ErrorResponseSerializer, 403: ErrorResponseSerializer},
    parameters=[
        OpenApiParameter(
            name="X-Tenant-ID",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.HEADER,
            required=True,
            description="Tenant UUID required for tenant-scoped billing close.",
        )
    ],
)
@api_view(["POST"])
@permission_classes([IsTenantAdminOrOwner])
def billing_invoice_close(request):
    serializer = BillingInvoiceCloseSerializer(data=request.data or {})
    if not serializer.is_valid():
        return Response({"error": "invalid payload", "detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    tenant = getattr(request, "tenant", None)
    if tenant is None:
        return Response({"error": "tenant not found", "request_id": _request_id(request)}, status=status.HTTP_400_BAD_REQUEST)
    subscription = get_latest_billable_subscription(tenant)
    if not subscription:
        return Response({"error": "active subscription not found", "request_id": _request_id(request)}, status=status.HTTP_400_BAD_REQUEST)

    payload = serializer.validated_data
    invoice = close_current_billing_period(
        tenant=tenant,
        subscription=subscription,
        active_users=payload.get("active_users"),
        api_requests=payload.get("api_requests"),
    )
    return Response(_serialize_invoice(invoice), status=status.HTTP_200_OK)


@extend_schema(
    operation_id="billing_invoice_latest",
    description="Get latest finalized invoice for tenant.",
    responses={200: BillingInvoiceSerializer, 404: ErrorResponseSerializer, 401: ErrorResponseSerializer, 403: ErrorResponseSerializer},
    parameters=[
        OpenApiParameter(
            name="X-Tenant-ID",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.HEADER,
            required=True,
            description="Tenant UUID required for tenant-scoped invoice access.",
        )
    ],
)
@api_view(["GET"])
@permission_classes([IsTenantAdminOrOwner])
def billing_invoice_latest(request):
    tenant = getattr(request, "tenant", None)
    if tenant is None:
        return Response({"error": "tenant not found", "request_id": _request_id(request)}, status=status.HTTP_400_BAD_REQUEST)

    invoice = BillingInvoice.objects.filter(tenant=tenant).order_by("-generated_at").first()
    if not invoice:
        return Response({"error": "invoice not found", "request_id": _request_id(request)}, status=status.HTTP_404_NOT_FOUND)
    return Response(_serialize_invoice(invoice), status=status.HTTP_200_OK)


@extend_schema(
    operation_id="billing_invoice_list",
    description="List latest tenant invoices.",
    responses={200: BillingInvoiceSerializer(many=True), 401: ErrorResponseSerializer, 403: ErrorResponseSerializer},
    parameters=[
        OpenApiParameter(
            name="X-Tenant-ID",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.HEADER,
            required=True,
            description="Tenant UUID required for tenant-scoped invoice listing.",
        )
    ],
)
@api_view(["GET"])
@permission_classes([IsTenantAdminOrOwner])
def billing_invoice_list(request):
    tenant = getattr(request, "tenant", None)
    if tenant is None:
        return Response({"error": "tenant not found", "request_id": _request_id(request)}, status=status.HTTP_400_BAD_REQUEST)
    invoices = BillingInvoice.objects.filter(tenant=tenant).order_by("-generated_at")[:24]
    return Response([_serialize_invoice(inv) for inv in invoices], status=status.HTTP_200_OK)


@extend_schema(
    operation_id="billing_invoice_detail",
    description="Get invoice detail with line items.",
    responses={200: BillingInvoiceDetailSerializer, 404: ErrorResponseSerializer, 401: ErrorResponseSerializer, 403: ErrorResponseSerializer},
    parameters=[
        OpenApiParameter(
            name="X-Tenant-ID",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.HEADER,
            required=True,
            description="Tenant UUID required for tenant-scoped invoice detail.",
        )
    ],
)
@api_view(["GET"])
@permission_classes([IsTenantAdminOrOwner])
def billing_invoice_detail(request, invoice_id):
    tenant = getattr(request, "tenant", None)
    if tenant is None:
        return Response({"error": "tenant not found", "request_id": _request_id(request)}, status=status.HTTP_400_BAD_REQUEST)
    invoice = BillingInvoice.objects.filter(tenant=tenant, invoice_id=invoice_id).first()
    if not invoice:
        return Response({"error": "invoice not found", "request_id": _request_id(request)}, status=status.HTTP_404_NOT_FOUND)
    return Response(_serialize_invoice_detail(invoice), status=status.HTTP_200_OK)


@extend_schema(
    operation_id="billing_invoice_receipt",
    description="Download plain-text receipt for invoice.",
    responses={200: OpenApiTypes.STR, 404: ErrorResponseSerializer, 401: ErrorResponseSerializer, 403: ErrorResponseSerializer},
    parameters=[
        OpenApiParameter(
            name="X-Tenant-ID",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.HEADER,
            required=True,
            description="Tenant UUID required for tenant-scoped receipt download.",
        )
    ],
)
@api_view(["GET"])
@permission_classes([IsTenantAdminOrOwner])
def billing_invoice_receipt(request, invoice_id):
    tenant = getattr(request, "tenant", None)
    if tenant is None:
        return Response({"error": "tenant not found", "request_id": _request_id(request)}, status=status.HTTP_400_BAD_REQUEST)
    invoice = BillingInvoice.objects.filter(tenant=tenant, invoice_id=invoice_id).first()
    if not invoice:
        return Response({"error": "invoice not found", "request_id": _request_id(request)}, status=status.HTTP_404_NOT_FOUND)

    lines = list(BillingInvoiceLineItem.objects.filter(invoice=invoice).order_by("id"))
    receipt_lines = [
        "CliniGraph AI Receipt",
        f"Tenant: {tenant.name}",
        f"Invoice ID: {invoice.invoice_id}",
        f"Period: {invoice.period_start.isoformat()} - {invoice.period_end.isoformat()}",
        f"Currency: {invoice.currency}",
        "",
        "Line Items:",
    ]
    for line in lines:
        receipt_lines.append(
            f"- {line.description}: qty={line.quantity}, unit={line.unit_price_cents}, total={line.total_price_cents}"
        )
    receipt_lines.append("")
    receipt_lines.append(f"Total (cents): {invoice.total_cents}")
    content = "\n".join(receipt_lines)

    response = HttpResponse(content, content_type="text/plain; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="invoice-{invoice.invoice_id}.txt"'
    return response


@extend_schema(
    operation_id="billing_invoice_receipt_pdf",
    description="Download PDF receipt for invoice.",
    responses={200: OpenApiTypes.BINARY, 404: ErrorResponseSerializer, 401: ErrorResponseSerializer, 403: ErrorResponseSerializer},
    parameters=[
        OpenApiParameter(
            name="X-Tenant-ID",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.HEADER,
            required=True,
            description="Tenant UUID required for tenant-scoped receipt download.",
        )
    ],
)
@api_view(["GET"])
@permission_classes([IsTenantAdminOrOwner])
def billing_invoice_receipt_pdf(request, invoice_id):
    tenant = getattr(request, "tenant", None)
    if tenant is None:
        return Response({"error": "tenant not found", "request_id": _request_id(request)}, status=status.HTTP_400_BAD_REQUEST)
    invoice = BillingInvoice.objects.filter(tenant=tenant, invoice_id=invoice_id).first()
    if not invoice:
        return Response({"error": "invoice not found", "request_id": _request_id(request)}, status=status.HTTP_404_NOT_FOUND)

    line_items = list(BillingInvoiceLineItem.objects.filter(invoice=invoice).order_by("id"))
    try:
        pdf_bytes = render_invoice_pdf(invoice=invoice, tenant=tenant, line_items=line_items)
    except RuntimeError as exc:
        return Response({"error": "pdf rendering unavailable", "detail": str(exc), "request_id": _request_id(request)}, status=status.HTTP_400_BAD_REQUEST)

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="invoice-{invoice.invoice_id}.pdf"'
    return response


@extend_schema(
    operation_id="billing_invoice_export_csv",
    description="Export tenant invoices as CSV for finance/accounting workflows.",
    responses={200: OpenApiTypes.BINARY, 401: ErrorResponseSerializer, 403: ErrorResponseSerializer},
    parameters=[
        OpenApiParameter(
            name="X-Tenant-ID",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.HEADER,
            required=True,
            description="Tenant UUID required for tenant-scoped CSV export.",
        ),
        OpenApiParameter(
            name="status",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Optional invoice status filter (draft/finalized/paid/void).",
        ),
        OpenApiParameter(
            name="currency",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Optional ISO currency filter, e.g. USD.",
        ),
        OpenApiParameter(
            name="start_date",
            type=OpenApiTypes.DATE,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Include invoices generated on/after date (YYYY-MM-DD).",
        ),
        OpenApiParameter(
            name="end_date",
            type=OpenApiTypes.DATE,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Include invoices generated on/before date (YYYY-MM-DD).",
        ),
        OpenApiParameter(
            name="period_start",
            type=OpenApiTypes.DATE,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Include invoices whose billed period starts on/after date (YYYY-MM-DD).",
        ),
        OpenApiParameter(
            name="period_end",
            type=OpenApiTypes.DATE,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Include invoices whose billed period ends on/before date (YYYY-MM-DD).",
        ),
    ],
)
@api_view(["GET"])
@permission_classes([IsTenantAdminOrOwner])
def billing_invoice_export_csv(request):
    tenant = getattr(request, "tenant", None)
    if tenant is None:
        return Response({"error": "tenant not found", "request_id": _request_id(request)}, status=status.HTTP_400_BAD_REQUEST)

    invoices_qs = BillingInvoice.objects.filter(tenant=tenant).order_by("-generated_at")
    status_filter = (request.query_params.get("status") or "").strip()
    currency_filter = (request.query_params.get("currency") or "").strip().upper()
    start_date_raw = (request.query_params.get("start_date") or "").strip()
    end_date_raw = (request.query_params.get("end_date") or "").strip()
    period_start_raw = (request.query_params.get("period_start") or "").strip()
    period_end_raw = (request.query_params.get("period_end") or "").strip()

    start_date = None
    end_date = None
    period_start_filter = None
    period_end_filter = None

    if start_date_raw:
        try:
            start_date = parse_date(start_date_raw)
        except ValueError:
            start_date = None
        if start_date is None:
            return Response({"error": "invalid start_date format", "request_id": _request_id(request)}, status=status.HTTP_400_BAD_REQUEST)
        invoices_qs = invoices_qs.filter(generated_at__date__gte=start_date)

    if end_date_raw:
        try:
            end_date = parse_date(end_date_raw)
        except ValueError:
            end_date = None
        if end_date is None:
            return Response({"error": "invalid end_date format", "request_id": _request_id(request)}, status=status.HTTP_400_BAD_REQUEST)
        invoices_qs = invoices_qs.filter(generated_at__date__lte=end_date)

    if period_start_raw:
        try:
            period_start_filter = parse_date(period_start_raw)
        except ValueError:
            period_start_filter = None
        if period_start_filter is None:
            return Response({"error": "invalid period_start format", "request_id": _request_id(request)}, status=status.HTTP_400_BAD_REQUEST)
        invoices_qs = invoices_qs.filter(period_start__date__gte=period_start_filter)

    if period_end_raw:
        try:
            period_end_filter = parse_date(period_end_raw)
        except ValueError:
            period_end_filter = None
        if period_end_filter is None:
            return Response({"error": "invalid period_end format", "request_id": _request_id(request)}, status=status.HTTP_400_BAD_REQUEST)
        invoices_qs = invoices_qs.filter(period_end__date__lte=period_end_filter)

    if start_date_raw and end_date_raw and start_date > end_date:
        return Response({"error": "start_date must be <= end_date", "request_id": _request_id(request)}, status=status.HTTP_400_BAD_REQUEST)

    if period_start_raw and period_end_raw and period_start_filter > period_end_filter:
        return Response({"error": "period_start must be <= period_end", "request_id": _request_id(request)}, status=status.HTTP_400_BAD_REQUEST)

    if status_filter:
        invoices_qs = invoices_qs.filter(status=status_filter)
    if currency_filter:
        invoices_qs = invoices_qs.filter(currency=currency_filter)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "invoice_id",
        "period_start",
        "period_end",
        "status",
        "currency",
        "platform_fee_cents",
        "users_overage_cents",
        "api_overage_cents",
        "total_cents",
        "active_users",
        "api_requests",
        "overage_users",
        "overage_api_requests",
        "generated_at",
    ])
    for invoice in invoices_qs.iterator():
        writer.writerow([
            str(invoice.invoice_id),
            invoice.period_start.isoformat(),
            invoice.period_end.isoformat(),
            invoice.status,
            invoice.currency,
            invoice.platform_fee_cents,
            invoice.users_overage_cents,
            invoice.api_overage_cents,
            invoice.total_cents,
            invoice.active_users,
            invoice.api_requests,
            invoice.overage_users,
            invoice.overage_api_requests,
            invoice.generated_at.isoformat(),
        ])

    content = output.getvalue()
    response = HttpResponse(content, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="billing-export-{tenant.tenant_id}.csv"'
    return response


@extend_schema(
    operation_id="billing_usage_summary",
    description="Current billing period usage and overage summary for tenant.",
    responses={200: BillingUsageSummaryResponseSerializer, 400: ErrorResponseSerializer, 401: ErrorResponseSerializer, 403: ErrorResponseSerializer},
    parameters=[
        OpenApiParameter(
            name="X-Tenant-ID",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.HEADER,
            required=True,
            description="Tenant UUID required for tenant-scoped usage summary.",
        )
    ],
)
@api_view(["GET"])
@permission_classes([IsTenantAdminOrOwner])
def billing_usage_summary(request):
    tenant = getattr(request, "tenant", None)
    if tenant is None:
        return Response({"error": "tenant not found", "request_id": _request_id(request)}, status=status.HTTP_400_BAD_REQUEST)

    subscription = get_latest_billable_subscription(tenant)
    if not subscription:
        return Response({"error": "active subscription not found", "request_id": _request_id(request)}, status=status.HTTP_400_BAD_REQUEST)

    estimate = estimate_hybrid_monthly_bill(tenant=tenant, plan=subscription.plan)
    latest_invoice = BillingInvoice.objects.filter(tenant=tenant).order_by("-generated_at").first()
    return Response(
        {
            "tenant_id": tenant.tenant_id,
            "period_start": estimate.period_start,
            "period_end": estimate.period_end,
            "active_users": estimate.active_users,
            "api_requests": estimate.api_requests,
            "included_users": estimate.included_users,
            "included_api_requests": estimate.included_api_requests,
            "overage_users": estimate.overage_users,
            "overage_api_requests": estimate.overage_api_requests,
            "latest_invoice": _serialize_invoice(latest_invoice),
        },
        status=status.HTTP_200_OK,
    )


@extend_schema(
    operation_id="subscription_create",
    description="Create tenant + subscription draft with trial period (payment-provider integration ready).",
    request=SubscriptionCreateSerializer,
    responses={
        200: SubscriptionCreateResponseSerializer,
        400: ErrorResponseSerializer,
        401: ErrorResponseSerializer,
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def subscription_create(request):
    serializer = SubscriptionCreateSerializer(data=request.data or {})
    if not serializer.is_valid():
        return Response({"error": "invalid payload", "detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    payload = serializer.validated_data
    plan = get_active_plan_or_none(payload["plan_code"])
    if not plan:
        return Response({"error": "plan not found", "request_id": _request_id(request)}, status=status.HTTP_400_BAD_REQUEST)
    result = create_subscription_draft(
        user=request.user,
        tenant_name=payload.get("tenant_name") or "",
        tenant_type=payload.get("tenant_type", "individual"),
        plan=plan,
        trial_days=payload.get("trial_days"),
    )

    return Response(
        {
            "tenant_id": result.tenant.tenant_id,
            "subscription_id": int(result.subscription.pk or 0),
            "status": result.subscription.status,
            "trial_ends_at": result.subscription.trial_ends_at,
            "checkout_hint": "Integrate Stripe/Adyen checkout URL in next phase.",
        },
        status=status.HTTP_200_OK,
    )


@extend_schema(
    operation_id="billing_checkout_session_create",
    description="Create a Stripe Checkout session for a SaaS subscription.",
    request=CheckoutSessionCreateSerializer,
    responses={200: CheckoutSessionResponseSerializer, 400: ErrorResponseSerializer, 401: ErrorResponseSerializer},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def billing_checkout_session_create(request):
    serializer = CheckoutSessionCreateSerializer(data=request.data or {})
    if not serializer.is_valid():
        return Response({"error": "invalid payload", "detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    payload = serializer.validated_data
    plan = get_active_plan_or_none(payload["plan_code"])
    if not plan:
        return Response({"error": "plan not found", "request_id": _request_id(request)}, status=status.HTTP_400_BAD_REQUEST)
    try:
        result = create_checkout_session(
            user=request.user,
            tenant_name=payload.get("tenant_name") or "",
            tenant_type=payload.get("tenant_type", "individual"),
            plan=plan,
        )
    except BillingConfigurationError as exc:
        return Response({"error": "billing not configured", "detail": str(exc), "request_id": _request_id(request)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(
        {
            "tenant_id": result.tenant.tenant_id,
            "subscription_id": int(result.subscription.pk or 0),
            "provider": "stripe",
            "checkout_url": getattr(result.session, "url", "") or "",
            "checkout_session_id": getattr(result.session, "id", "") or "",
        },
        status=status.HTTP_200_OK,
    )


@extend_schema(
    operation_id="billing_portal_session_create",
    description="Create Stripe customer portal session for subscription management.",
    request=BillingPortalSessionSerializer,
    responses={200: BillingPortalSessionResponseSerializer, 400: ErrorResponseSerializer, 401: ErrorResponseSerializer, 403: ErrorResponseSerializer},
    parameters=[
        OpenApiParameter(
            name="X-Tenant-ID",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.HEADER,
            required=True,
            description="Tenant UUID required for tenant-scoped billing portal.",
        )
    ],
)
@api_view(["POST"])
@permission_classes([IsTenantAdminOrOwner])
def billing_portal_session_create(request):
    serializer = BillingPortalSessionSerializer(data=request.data or {})
    if not serializer.is_valid():
        return Response({"error": "invalid payload", "detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    tenant = getattr(request, "tenant", None)
    if tenant is None:
        return Response({"error": "tenant not found", "request_id": _request_id(request)}, status=status.HTTP_400_BAD_REQUEST)
    subscription = get_latest_billable_subscription(tenant)
    if not subscription:
        return Response({"error": "active subscription not found", "request_id": _request_id(request)}, status=status.HTTP_400_BAD_REQUEST)
    if not subscription.provider_customer_id:
        return Response({"error": "stripe customer not linked", "request_id": _request_id(request)}, status=status.HTTP_400_BAD_REQUEST)

    try:
        session = create_portal_session(subscription=subscription, return_url=serializer.validated_data.get("return_url") or None)
    except BillingConfigurationError as exc:
        return Response({"error": "billing not configured", "detail": str(exc), "request_id": _request_id(request)}, status=status.HTTP_400_BAD_REQUEST)

    return Response(
        {
            "portal_url": getattr(session, "url", "") or "",
            "session_id": getattr(session, "id", "") or "",
        },
        status=status.HTTP_200_OK,
    )


@extend_schema(
    operation_id="billing_subscription_change_plan",
    description="Preview and optionally apply Stripe plan change with proration.",
    request=SubscriptionPlanChangeSerializer,
    responses={200: SubscriptionPlanChangeResponseSerializer, 400: ErrorResponseSerializer, 401: ErrorResponseSerializer, 403: ErrorResponseSerializer},
    parameters=[
        OpenApiParameter(
            name="X-Tenant-ID",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.HEADER,
            required=True,
            description="Tenant UUID required for tenant-scoped subscription changes.",
        )
    ],
)
@api_view(["POST"])
@permission_classes([IsTenantAdminOrOwner])
def billing_subscription_change_plan(request):
    serializer = SubscriptionPlanChangeSerializer(data=request.data or {})
    if not serializer.is_valid():
        return Response({"error": "invalid payload", "detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    tenant = getattr(request, "tenant", None)
    if tenant is None:
        return Response({"error": "tenant not found", "request_id": _request_id(request)}, status=status.HTTP_400_BAD_REQUEST)
    subscription = get_latest_billable_subscription(tenant)
    if not subscription:
        return Response({"error": "active subscription not found", "request_id": _request_id(request)}, status=status.HTTP_400_BAD_REQUEST)
    if not subscription.provider_subscription_id:
        return Response({"error": "stripe subscription not linked", "request_id": _request_id(request)}, status=status.HTTP_400_BAD_REQUEST)

    target_plan = get_active_plan_or_none(serializer.validated_data["target_plan_code"])
    if not target_plan:
        return Response({"error": "target plan not found", "request_id": _request_id(request)}, status=status.HTTP_400_BAD_REQUEST)
    if not target_plan.provider_price_id:
        return Response({"error": "target plan missing stripe price", "request_id": _request_id(request)}, status=status.HTTP_400_BAD_REQUEST)

    previous_plan_code = subscription.plan.code
    try:
        result = change_subscription_plan(
            subscription=subscription,
            target_plan=target_plan,
            apply_change=bool(serializer.validated_data.get("apply", False)),
        )
    except BillingConfigurationError as exc:
        return Response({"error": "billing not configured", "detail": str(exc), "request_id": _request_id(request)}, status=status.HTTP_400_BAD_REQUEST)

    return Response(
        {
            "subscription_id": int(subscription.pk or 0),
            "previous_plan_code": previous_plan_code,
            "target_plan_code": target_plan.code,
            "applied": result.applied,
            "proration_preview": result.preview,
        },
        status=status.HTTP_200_OK,
    )


@extend_schema(
    operation_id="usage_ingest",
    description="Internal usage ingestion endpoint for quota and billing analytics.",
    request=UsageIngestSerializer,
    responses={200: OpenApiTypes.OBJECT, 400: ErrorResponseSerializer, 401: ErrorResponseSerializer, 403: ErrorResponseSerializer},
    parameters=[
        OpenApiParameter(
            name="X-API-Key",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.HEADER,
            required=True,
            description="Internal service API key.",
        )
    ],
    auth=["ApiKeyAuth"],
)
@api_view(["POST"])
@permission_classes([HasAgentApiKeyOrAuthenticated])
def usage_ingest(request):
    serializer = UsageIngestSerializer(data=request.data or {})
    if not serializer.is_valid():
        return Response({"error": "invalid payload", "detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    payload = serializer.validated_data
    try:
        tenant = Tenant.objects.get(tenant_id=payload["tenant_id"], is_active=True)
    except Tenant.DoesNotExist:
        return Response({"error": "tenant not found", "request_id": _request_id(request)}, status=status.HTTP_400_BAD_REQUEST)

    UsageRecord.objects.create(
        tenant=tenant,
        metric=payload["metric"],
        quantity=payload.get("quantity", 1),
        meta=payload.get("meta", {}),
    )
    incr("billing.usage_events.total")
    return Response({"status": "ok", "request_id": _request_id(request)}, status=status.HTTP_200_OK)


@extend_schema(
    operation_id="billing_webhook",
    description="Billing webhook receiver (provider-agnostic foundation; add Stripe signature verification next).",
    request=BillingWebhookSerializer,
    responses={200: OpenApiTypes.OBJECT, 400: ErrorResponseSerializer, 401: ErrorResponseSerializer},
    auth=[],
)
@api_view(["POST"])
def billing_webhook(request):
    stripe_signature = request.headers.get("Stripe-Signature")
    if stripe_signature:
        try:
            provider = StripeBillingProvider()
            event = provider.construct_event(request.body, stripe_signature)
        except BillingConfigurationError as exc:
            return Response({"error": "billing not configured", "detail": str(exc), "request_id": _request_id(request)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response({"error": "invalid stripe webhook", "detail": str(exc), "request_id": _request_id(request)}, status=status.HTTP_400_BAD_REQUEST)

        event_type = getattr(event, "type", "") or ""
        data_object = event["data"]["object"]
        tenant = None
        subscription = None
        metadata = data_object.get("metadata", {}) if isinstance(data_object, dict) else {}
        tenant_uuid = metadata.get("tenant_id")
        if tenant_uuid:
            tenant = Tenant.objects.filter(tenant_id=tenant_uuid).first()
        sub_id = metadata.get("subscription_id")
        if sub_id:
            subscription = Subscription.objects.filter(pk=sub_id).first()

        if event_type == "checkout.session.completed":
            if subscription:
                subscription.status = Subscription.Status.ACTIVE
                subscription.provider_customer_id = data_object.get("customer", "") or subscription.provider_customer_id
                subscription.save(update_fields=["status", "provider_customer_id", "updated_at"])
        elif event_type in {"customer.subscription.updated", "customer.subscription.created"}:
            provider_subscription_id = data_object.get("id", "")
            if not subscription and tenant and provider_subscription_id:
                subscription = Subscription.objects.filter(tenant=tenant, provider_subscription_id=provider_subscription_id).first()
            if subscription:
                stripe_status = (data_object.get("status", "") or "").lower()
                subscription.provider_subscription_id = provider_subscription_id or subscription.provider_subscription_id
                subscription.provider_customer_id = data_object.get("customer", "") or subscription.provider_customer_id
                subscription.status = Subscription.Status.ACTIVE if stripe_status in {"active", "trialing"} else Subscription.Status.PAST_DUE
                subscription.save(update_fields=["provider_subscription_id", "provider_customer_id", "status", "updated_at"])
        elif event_type in {"customer.subscription.deleted"}:
            provider_subscription_id = data_object.get("id", "")
            if provider_subscription_id:
                subscription = Subscription.objects.filter(provider_subscription_id=provider_subscription_id).first()
            if subscription:
                subscription.status = Subscription.Status.CANCELED
                subscription.canceled_at = timezone.now()
                subscription.save(update_fields=["status", "canceled_at", "updated_at"])
        elif event_type == "invoice.payment_failed":
            provider_subscription_id = data_object.get("subscription", "")
            if provider_subscription_id:
                subscription = Subscription.objects.filter(provider_subscription_id=provider_subscription_id).first()
            if subscription:
                subscription.status = Subscription.Status.PAST_DUE
                subscription.save(update_fields=["status", "updated_at"])

        BillingEvent.objects.create(
            tenant=tenant,
            event_type=event_type,
            provider="stripe",
            provider_event_id=getattr(event, "id", "") or "",
            status="received",
            payload=data_object if isinstance(data_object, dict) else {},
        )
        incr("billing.events.total")
        return Response({"status": "accepted", "request_id": _request_id(request)}, status=status.HTTP_200_OK)

    expected = (getattr(settings, "BILLING_WEBHOOK_SECRET", "") or "").strip()
    provided = (request.headers.get("X-Billing-Webhook-Secret") or "").strip()
    if expected and not (provided and secrets.compare_digest(expected, provided)):
        return Response({"error": "invalid webhook secret", "request_id": _request_id(request)}, status=status.HTTP_401_UNAUTHORIZED)

    serializer = BillingWebhookSerializer(data=request.data or {})
    if not serializer.is_valid():
        return Response({"error": "invalid payload", "detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    payload = serializer.validated_data
    tenant = None
    if payload.get("tenant_id"):
        tenant = Tenant.objects.filter(tenant_id=payload["tenant_id"]).first()

    BillingEvent.objects.create(
        tenant=tenant,
        event_type=payload["event_type"],
        provider=payload["provider"],
        provider_event_id=payload.get("provider_event_id", ""),
        status="received",
        payload=payload.get("payload", {}),
    )
    incr("billing.events.total")
    return Response({"status": "accepted", "request_id": _request_id(request)}, status=status.HTTP_200_OK)
