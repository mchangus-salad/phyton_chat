"""
Mobile API views.

Provides simplified endpoints optimised for iOS and Android clients:
  - Device token registration (push notifications)
  - Patient case upload with PHI de-identification
  - Evidence viewer search

All endpoints require JWT authentication and an X-Tenant-ID header.
The same RBAC rules as the web platform apply (clinician role or above).
"""

import hashlib
import logging

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes, throttle_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response

from .agent_ai.file_extractor import extract_text
from .agent_ai.phi_deidentifier import deidentify
from .models import DeviceToken, PatientCaseSession, Tenant
from .permissions import HasLlmAccessOrApiKey, IsTenantClinicianOrAbove
from .serializers import (
    DeviceTokenRegisterSerializer,
    DeviceTokenResponseSerializer,
    ErrorResponseSerializer,
    MobileCaseUploadResponseSerializer,
    MobileCaseUploadSerializer,
    MobileEvidenceQuerySerializer,
    MobileEvidenceResponseSerializer,
)
from .throttles import AgentUserRateThrottle, TenantPlanQuotaThrottle

logger = logging.getLogger(__name__)

# Module-level service cache (same pattern as views.py).
_MOBILE_SERVICES: dict = {}


def _get_service(domain: str | None = None):
    """Return (or create) a cached AgentAIService for the given domain."""
    key = domain or 'medical'
    if key not in _MOBILE_SERVICES:
        from .agent_ai.service import CliniGraphService
        _MOBILE_SERVICES[key] = CliniGraphService(domain=domain)
    return _MOBILE_SERVICES[key]


def _resolve_tenant(request):
    """Return the Tenant already set by the permission class, or look it up from header."""
    if hasattr(request, 'tenant') and request.tenant is not None:
        return request.tenant
    tenant_id = request.headers.get('X-Tenant-ID', '').strip()
    if not tenant_id:
        return None
    try:
        return Tenant.objects.get(tenant_id=tenant_id)
    except (Tenant.DoesNotExist, ValueError):
        return None


# ── Device token registration ─────────────────────────────────────────────────

@extend_schema(
    request=DeviceTokenRegisterSerializer,
    responses={201: DeviceTokenResponseSerializer, 400: ErrorResponseSerializer, 403: ErrorResponseSerializer},
    tags=['mobile'],
    summary='Register push notification device token',
    description=(
        'Register or refresh an FCM (Android) or APNs (iOS) device token for '
        'push notification delivery. If the same token already exists for this '
        'user/tenant pair, the existing record is updated (upsert).'
    ),
)
@api_view(['POST'])
@permission_classes([IsTenantClinicianOrAbove])
@throttle_classes([AgentUserRateThrottle])
def mobile_device_register(request):
    serializer = DeviceTokenRegisterSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    tenant = _resolve_tenant(request)
    if tenant is None:
        return Response({'error': 'X-Tenant-ID header is required.'}, status=status.HTTP_400_BAD_REQUEST)

    validated = serializer.validated_data
    device, _ = DeviceToken.objects.update_or_create(
        user=request.user,
        tenant=tenant,
        token=validated['token'],
        defaults={
            'platform': validated['platform'],
            'device_label': validated.get('device_label', ''),
            'app_version': validated.get('app_version', ''),
            'is_active': True,
        },
    )

    response_serializer = DeviceTokenResponseSerializer({
        'device_id': device.device_id,
        'platform': device.platform,
        'device_label': device.device_label,
        'is_active': device.is_active,
        'registered_at': device.registered_at,
    })
    return Response(response_serializer.data, status=status.HTTP_201_CREATED)


@extend_schema(
    responses={204: None, 400: ErrorResponseSerializer, 404: ErrorResponseSerializer},
    tags=['mobile'],
    summary='Deregister push notification device token',
    description='Mark a device token as inactive. The token will no longer receive push notifications.',
)
@api_view(['DELETE'])
@permission_classes([IsTenantClinicianOrAbove])
@throttle_classes([AgentUserRateThrottle])
def mobile_device_deregister(request, token):
    tenant = _resolve_tenant(request)
    if tenant is None:
        return Response({'error': 'X-Tenant-ID header is required.'}, status=status.HTTP_400_BAD_REQUEST)

    updated = DeviceToken.objects.filter(
        user=request.user,
        tenant=tenant,
        token=token,
        is_active=True,
    ).update(is_active=False)

    if not updated:
        return Response({'error': 'Device token not found.'}, status=status.HTTP_404_NOT_FOUND)

    return Response(status=status.HTTP_204_NO_CONTENT)


# ── Mobile patient case upload ────────────────────────────────────────────────

@extend_schema(
    request={'multipart/form-data': MobileCaseUploadSerializer},
    responses={201: MobileCaseUploadResponseSerializer, 400: ErrorResponseSerializer, 403: ErrorResponseSerializer},
    tags=['mobile'],
    summary='Upload patient case from mobile device',
    description=(
        'Upload a patient case document (PDF or plain text) from a mobile device. '
        'The document is de-identified according to HIPAA Safe Harbor rules before '
        'any AI processing. RAW PHI is never persisted. '
        'Returns a session_id and redaction summary.'
    ),
)
@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
@permission_classes([HasLlmAccessOrApiKey])
@throttle_classes([AgentUserRateThrottle, TenantPlanQuotaThrottle])
def mobile_case_upload(request):
    serializer = MobileCaseUploadSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    validated = serializer.validated_data
    uploaded_file = validated['file']
    domain = validated.get('domain', 'medical')

    # Extract plain text from the uploaded file (PDF, TXT, CSV supported).
    try:
        file_bytes = uploaded_file.read()
        raw_text = extract_text(uploaded_file.name, file_bytes)
    except Exception as exc:
        logger.warning("mobile_case_upload: text extraction failed file=%s err=%s", uploaded_file.name, exc)
        return Response({'error': 'Could not extract text from the uploaded file.'}, status=status.HTTP_400_BAD_REQUEST)

    # De-identify before any downstream processing.
    clean_text, redaction_summary = deidentify(raw_text)

    text_hash = hashlib.sha256(raw_text.encode('utf-8', errors='replace')).hexdigest()

    session = PatientCaseSession.objects.create(
        domain=domain,
        subdomain=validated.get('subdomain', ''),
        text_hash=text_hash,
        redaction_count=redaction_summary.total_redactions,
        redaction_categories=redaction_summary.categories,
        source_filename=uploaded_file.name[:255],
        user_id=str(request.user.pk) if request.user.is_authenticated else 'anonymous',
    )

    logger.info(
        "mobile_case_upload: session=%s domain=%s redactions=%d",
        session.session_id, domain, redaction_summary.total_redactions,
    )

    response_serializer = MobileCaseUploadResponseSerializer({
        'session_id': session.session_id,
        'domain': domain,
        'redaction_count': redaction_summary.total_redactions,
        'redaction_categories': redaction_summary.categories,
        'source_filename': uploaded_file.name,
        'created_at': session.created_at,
    })
    return Response(response_serializer.data, status=status.HTTP_201_CREATED)


# ── Mobile evidence viewer ────────────────────────────────────────────────────

@extend_schema(
    request=MobileEvidenceQuerySerializer,
    responses={200: MobileEvidenceResponseSerializer, 400: ErrorResponseSerializer},
    tags=['mobile'],
    summary='Search medical evidence (mobile)',
    description=(
        'Retrieve ranked evidence documents for a clinical query. '
        'Designed for a compact mobile evidence viewer: returns title, excerpt, '
        'source reference, and a relevance score for each result.'
    ),
)
@api_view(['POST'])
@permission_classes([HasLlmAccessOrApiKey])
@throttle_classes([AgentUserRateThrottle, TenantPlanQuotaThrottle])
def mobile_evidence_search(request):
    serializer = MobileEvidenceQuerySerializer(data=request.data)
    if not serializer.is_valid():
        return Response({'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    validated = serializer.validated_data
    query = validated['query']
    domain = validated.get('domain', 'medical')
    top_k = validated.get('top_k', 5)

    try:
        service = _get_service(domain)
        result = service.search_evidence(query=query, max_results=top_k)
    except Exception as exc:
        logger.error("mobile_evidence_search: domain=%s err=%s", domain, exc)
        return Response({'error': 'Evidence search unavailable.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    results = []
    for item in result.evidence:
        results.append({
            'rank': item.get('citation_id', ''),
            'title': item.get('title') or item.get('source', ''),
            'excerpt': item.get('text', ''),
            'source': item.get('source', ''),
            'score': item.get('score'),
        })

    # Renumber ranks sequentially.
    for i, r in enumerate(results, start=1):
        r['rank'] = i

    response_serializer = MobileEvidenceResponseSerializer({
        'results': results,
        'query': query,
        'domain': domain,
        'total': len(results),
    })
    return Response(response_serializer.data, status=status.HTTP_200_OK)



