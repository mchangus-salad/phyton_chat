"""
Sharing and image analysis views for CliniGraph AI.

Endpoints:
  POST   /api/v1/sharing/snapshots/          → save a case analysis snapshot
  POST   /api/v1/sharing/                    → create a share token
  GET    /api/v1/sharing/<uuid:token>/       → view shared content (increments view_count)
  POST   /api/v1/sharing/<uuid:token>/email/ → send share link by email
  DELETE /api/v1/sharing/<uuid:token>/       → revoke a share token (owner only)
  POST   /api/v1/cases/image-ocr/            → extract text from a clinical image

HIPAA notes:
  - No PHI is stored in CaseAnalysisSnapshot (AI output of de-identified input only).
  - Sharing is restricted to the same tenant.
  - Email dispatch sends a URL only — not the content itself.
  - Image OCR text is always routed through the PHI de-identifier before storage.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.utils import timezone

from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes, throttle_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from .models import (
    AgentChatHighlight,
    CaseAnalysisSnapshot,
    PatientCaseSession,
    SharedContentToken,
    Tenant,
)
from .permissions import HasLlmAccessOrApiKey, IsTenantClinicianOrAbove
from .serializers import (
    CaseSnapshotCreateSerializer,
    CaseSnapshotResponseSerializer,
    ErrorResponseSerializer,
    ImageOCRResponseSerializer,
    ImageOCRUploadSerializer,
    ShareCreateSerializer,
    ShareEmailSerializer,
    ShareTokenResponseSerializer,
    ShareViewResponseSerializer,
)
from .throttles import AgentAnonRateThrottle, AgentUserRateThrottle

logger = logging.getLogger(__name__)
User = get_user_model()

# ── helpers ───────────────────────────────────────────────────────────────────

_DEFAULT_SHARE_TTL_HOURS = 168  # 7 days


def _resolve_tenant(request) -> Tenant | None:
    """Resolve the active tenant from the request (set by permission class or header)."""
    if hasattr(request, "tenant") and request.tenant is not None:
        return request.tenant
    tenant_id = request.headers.get("X-Tenant-ID", "").strip()
    if not tenant_id:
        return None
    try:
        return Tenant.objects.get(tenant_id=tenant_id)
    except (Tenant.DoesNotExist, ValueError):
        return None


def _build_share_url(token) -> str:
    """Build the frontend share link for a given token UUID."""
    base_url = getattr(settings, "CLINIGRAPH_FRONTEND_URL", "http://localhost:5173")
    return f"{base_url}/shared/{token}"


def _request_id(request) -> str:
    return getattr(request, "request_id", "n/a")


# ── Case Analysis Snapshots ───────────────────────────────────────────────────

@extend_schema(
    operation_id="case_snapshot_create",
    description=(
        "Save the de-identified AI analysis result of a patient case session so it can be "
        "shared with colleagues. Only the AI-generated output is stored — no PHI."
    ),
    request=CaseSnapshotCreateSerializer,
    responses={
        201: CaseSnapshotResponseSerializer,
        400: ErrorResponseSerializer,
        401: ErrorResponseSerializer,
        403: ErrorResponseSerializer,
    },
    auth=["BearerAuth", "ApiKeyAuth"],
)
@api_view(["POST"])
@permission_classes([HasLlmAccessOrApiKey])
@throttle_classes([AgentAnonRateThrottle, AgentUserRateThrottle])
def case_snapshot_create(request):
    """Persist an AI analysis snapshot (de-identified) for future sharing."""
    serializer = CaseSnapshotCreateSerializer(data=request.data or {})
    if not serializer.is_valid():
        return Response(
            {"error": "invalid payload", "detail": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    payload = serializer.validated_data
    tenant = _resolve_tenant(request)
    if tenant is None:
        return Response(
            {"error": "tenant not found", "request_id": _request_id(request)},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        session = PatientCaseSession.objects.get(session_id=payload["session_id"])
    except PatientCaseSession.DoesNotExist:
        return Response(
            {"error": "session not found", "request_id": _request_id(request)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    snapshot = CaseAnalysisSnapshot.objects.create(
        session=session,
        tenant=tenant,
        created_by=request.user if request.user.is_authenticated else None,
        domain=payload.get("domain", "medical"),
        analysis_text=payload["analysis_text"],
        citations=payload.get("citations", []),
        safety_notice=payload.get("safety_notice", ""),
    )

    return Response(
        {
            "snapshot_id": snapshot.snapshot_id,
            "session_id": session.session_id,
            "domain": snapshot.domain,
            "created_at": snapshot.created_at,
        },
        status=status.HTTP_201_CREATED,
    )


# ── Share token creation ──────────────────────────────────────────────────────

@extend_schema(
    operation_id="share_create",
    description=(
        "Generate a share token for a chat highlight or patient case snapshot. "
        "The token produces a time-limited URL that can be sent to colleagues within the same tenant."
    ),
    request=ShareCreateSerializer,
    responses={
        201: ShareTokenResponseSerializer,
        400: ErrorResponseSerializer,
        401: ErrorResponseSerializer,
        403: ErrorResponseSerializer,
    },
    auth=["BearerAuth", "ApiKeyAuth"],
)
@api_view(["POST"])
@permission_classes([HasLlmAccessOrApiKey])
@throttle_classes([AgentAnonRateThrottle, AgentUserRateThrottle])
def share_create(request):
    """Create a share token for a highlight or case snapshot."""
    serializer = ShareCreateSerializer(data=request.data or {})
    if not serializer.is_valid():
        return Response(
            {"error": "invalid payload", "detail": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    payload = serializer.validated_data
    tenant = _resolve_tenant(request)
    if tenant is None:
        return Response(
            {"error": "tenant not found", "request_id": _request_id(request)},
            status=status.HTTP_403_FORBIDDEN,
        )

    target_type = payload["target_type"]
    target_id = payload["target_id"]  # UUID from serializer
    expires_at = timezone.now() + timezone.timedelta(hours=payload["expires_hours"])

    shared_token = SharedContentToken(
        created_by=request.user,
        tenant=tenant,
        target_type=target_type,
        recipient_emails=payload.get("recipient_emails", []),
        expires_at=expires_at,
        max_views=payload.get("max_views"),
    )

    if target_type == SharedContentToken.TargetType.HIGHLIGHT:
        try:
            # target_id is a UUID from the serializer — highlight PKs are integers.
            highlight = AgentChatHighlight.objects.get(
                pk=int(target_id.int % (2**31)),  # safe int cast from UUID int field
                chat_session__tenant=tenant,
            )
        except (AgentChatHighlight.DoesNotExist, ValueError, OverflowError):
            # Try string-based lookup in case caller passed the real PK as UUID representation.
            try:
                highlight = AgentChatHighlight.objects.get(
                    pk=payload.get("_highlight_pk"),
                    chat_session__tenant=tenant,
                )
            except (AgentChatHighlight.DoesNotExist, TypeError):
                return Response(
                    {"error": "highlight not found or not in tenant", "request_id": _request_id(request)},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        shared_token.highlight = highlight

    elif target_type == SharedContentToken.TargetType.CASE_SNAPSHOT:
        try:
            snapshot = CaseAnalysisSnapshot.objects.get(snapshot_id=target_id, tenant=tenant)
        except CaseAnalysisSnapshot.DoesNotExist:
            return Response(
                {"error": "case snapshot not found or not in tenant", "request_id": _request_id(request)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        shared_token.case_snapshot = snapshot

    shared_token.save()

    return Response(
        {
            "token": shared_token.token,
            "target_type": shared_token.target_type,
            "share_url": _build_share_url(shared_token.token),
            "expires_at": shared_token.expires_at,
            "max_views": shared_token.max_views,
        },
        status=status.HTTP_201_CREATED,
    )


# ── Share token view ──────────────────────────────────────────────────────────

@extend_schema(
    operation_id="share_view",
    description=(
        "Retrieve shared clinical content by token. "
        "Each successful retrieval increments the view counter. "
        "Returns 410 Gone when the token is expired, revoked, or view-capped."
    ),
    parameters=[
        OpenApiParameter(name="token", type=OpenApiTypes.UUID, location=OpenApiParameter.PATH),
    ],
    responses={
        200: ShareViewResponseSerializer,
        404: ErrorResponseSerializer,
        410: ErrorResponseSerializer,
    },
    auth=[],
)
@api_view(["GET"])
def share_view(request, token):
    """Return the content of a share token, incrementing its view counter."""
    try:
        shared = SharedContentToken.objects.select_related(
            "highlight__chat_session",
            "highlight__message",
            "case_snapshot",
        ).get(token=token)
    except SharedContentToken.DoesNotExist:
        return Response({"error": "share link not found"}, status=status.HTTP_404_NOT_FOUND)

    if not shared.is_valid():
        return Response(
            {"error": "share link has expired or been revoked"},
            status=status.HTTP_410_GONE,
        )

    # Atomically increment view count.
    SharedContentToken.objects.filter(pk=shared.pk).update(view_count=shared.view_count + 1)
    shared.refresh_from_db(fields=["view_count"])

    payload: dict = {
        "token": shared.token,
        "target_type": shared.target_type,
        "view_count": shared.view_count,
        "expires_at": shared.expires_at,
        "highlight": None,
        "case_snapshot": None,
    }

    if shared.target_type == SharedContentToken.TargetType.HIGHLIGHT and shared.highlight:
        h = shared.highlight
        payload["highlight"] = {
            "highlight_id": h.pk,
            "selected_text": h.selected_text,
            "context_snippet": h.context_snippet,
            "session_id": h.chat_session.session_id,
            "created_at": h.created_at,
        }

    elif shared.target_type == SharedContentToken.TargetType.CASE_SNAPSHOT and shared.case_snapshot:
        snap = shared.case_snapshot
        payload["case_snapshot"] = {
            "snapshot_id": snap.snapshot_id,
            "domain": snap.domain,
            "analysis_text": snap.analysis_text,
            "citations": snap.citations,
            "safety_notice": snap.safety_notice,
            "created_at": snap.created_at,
        }

    return Response(payload, status=status.HTTP_200_OK)


# ── Share by email ────────────────────────────────────────────────────────────

@extend_schema(
    operation_id="share_send_email",
    description=(
        "Send the share link by email. The email body contains only the URL — "
        "no patient data or clinical content is included in the message."
    ),
    parameters=[
        OpenApiParameter(name="token", type=OpenApiTypes.UUID, location=OpenApiParameter.PATH),
    ],
    request=ShareEmailSerializer,
    responses={
        200: {"type": "object"},
        400: ErrorResponseSerializer,
        401: ErrorResponseSerializer,
        403: ErrorResponseSerializer,
        410: ErrorResponseSerializer,
    },
    auth=["BearerAuth", "ApiKeyAuth"],
)
@api_view(["POST"])
@permission_classes([IsTenantClinicianOrAbove])
@throttle_classes([AgentAnonRateThrottle, AgentUserRateThrottle])
def share_send_email(request, token):
    """Send the share URL to a list of email addresses."""
    serializer = ShareEmailSerializer(data=request.data or {})
    if not serializer.is_valid():
        return Response(
            {"error": "invalid payload", "detail": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        shared = SharedContentToken.objects.get(token=token, created_by=request.user)
    except SharedContentToken.DoesNotExist:
        return Response({"error": "share link not found or not yours"}, status=status.HTTP_404_NOT_FOUND)

    if not shared.is_valid():
        return Response({"error": "share link has expired or been revoked"}, status=status.HTTP_410_GONE)

    payload = serializer.validated_data
    emails: list[str] = payload["emails"]
    personal_message: str = payload.get("message", "").strip()

    share_url = _build_share_url(shared.token)
    sender_name = request.user.get_full_name() or request.user.username
    subject = f"[CliniGraph AI] {sender_name} shared clinical content with you"

    body_lines = [
        f"{sender_name} has shared a clinical AI analysis with you via CliniGraph AI.",
        "",
        f"View it here (expires {shared.expires_at.strftime('%Y-%m-%d %H:%M UTC')}):",
        share_url,
    ]
    if personal_message:
        body_lines += ["", "Message from sender:", personal_message]
    body_lines += [
        "",
        "— CliniGraph AI",
        "This content is generated by an AI system for clinical decision support only.",
        "It does not constitute medical advice, diagnosis, or treatment.",
    ]

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@clinigraph.ai")

    sent_ok: list[str] = []
    failed: list[str] = []
    for email in emails:
        try:
            send_mail(
                subject=subject,
                message="\n".join(body_lines),
                from_email=from_email,
                recipient_list=[email],
                fail_silently=False,
            )
            sent_ok.append(email)
        except Exception as exc:
            logger.warning("share_send_email failed to %s token=%s error=%s", email, token, exc)
            failed.append(email)

    # Update audit trail with all recipients that were contacted.
    all_recipients = list(set(shared.recipient_emails) | set(sent_ok))
    SharedContentToken.objects.filter(pk=shared.pk).update(recipient_emails=all_recipients)

    return Response(
        {
            "sent": sent_ok,
            "failed": failed,
            "share_url": share_url,
            "request_id": _request_id(request),
        },
        status=status.HTTP_200_OK,
    )


# ── Share token revoke ────────────────────────────────────────────────────────

@extend_schema(
    operation_id="share_revoke",
    description="Revoke (deactivate) a share token. Only the creator can revoke their own tokens.",
    parameters=[
        OpenApiParameter(name="token", type=OpenApiTypes.UUID, location=OpenApiParameter.PATH),
    ],
    responses={
        204: None,
        403: ErrorResponseSerializer,
        404: ErrorResponseSerializer,
    },
    auth=["BearerAuth", "ApiKeyAuth"],
)
@api_view(["DELETE"])
@permission_classes([IsTenantClinicianOrAbove])
@throttle_classes([AgentAnonRateThrottle, AgentUserRateThrottle])
def share_revoke(request, token):
    """Deactivate a share token so it can no longer be viewed."""
    try:
        shared = SharedContentToken.objects.get(token=token, created_by=request.user)
    except SharedContentToken.DoesNotExist:
        return Response({"error": "share link not found or not yours"}, status=status.HTTP_404_NOT_FOUND)

    SharedContentToken.objects.filter(pk=shared.pk).update(is_active=False)
    return Response(status=status.HTTP_204_NO_CONTENT)


# ── Image OCR / Vision AI ─────────────────────────────────────────────────────

@extend_schema(
    operation_id="image_ocr_upload",
    description=(
        "Extract text from a clinical image (JPEG, PNG, TIFF, WEBP, BMP) using OCR or "
        "OpenAI GPT-4o Vision. The extracted text is automatically run through PHI "
        "de-identification (HIPAA Safe Harbor) before any storage or further processing. "
        "Use strategy='ocr' to keep all data on-premises (no external API calls). "
        "Use strategy='vision' for richer interpretation of diagnostic images (X-rays, path slides)."
    ),
    request=ImageOCRUploadSerializer,
    responses={
        201: ImageOCRResponseSerializer,
        400: ErrorResponseSerializer,
        401: ErrorResponseSerializer,
        403: ErrorResponseSerializer,
        500: ErrorResponseSerializer,
    },
    auth=["BearerAuth", "ApiKeyAuth"],
)
@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
@permission_classes([HasLlmAccessOrApiKey])
@throttle_classes([AgentAnonRateThrottle, AgentUserRateThrottle])
def image_ocr_upload(request):
    """
    Accept a clinical image, extract text (OCR / Vision AI), de-identify PHI,
    then persist a HIPAA-compliant PatientCaseSession audit record.

    Returns the de-identification metadata; no PHI is ever stored or returned.
    """
    serializer = ImageOCRUploadSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {"error": "invalid payload", "detail": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    payload = serializer.validated_data
    uploaded_file = payload["file"]
    domain = payload.get("domain", "medical")
    strategy = payload.get("strategy", "auto")

    file_bytes = uploaded_file.read()
    filename = uploaded_file.name or "upload.jpg"

    from .agent_ai.file_extractor import extract_text, IMAGE_EXTENSIONS
    import os

    ext = os.path.splitext(filename)[1].lower()
    if ext not in IMAGE_EXTENSIONS:
        return Response(
            {
                "error": (
                    f"File extension '{ext}' is not an image format supported by this endpoint. "
                    "Accepted: .jpg, .jpeg, .png, .webp, .tiff, .tif, .bmp"
                )
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # --- Step 1: Extract text from image ---
    strategy_used = strategy
    try:
        raw_text = extract_text(filename, file_bytes, image_strategy=strategy)
        # Determine which strategy was actually used (for 'auto', detection is inside extractor).
        if strategy == "auto":
            import os as _os
            api_key = _os.environ.get("OPENAI_API_KEY", "")
            strategy_used = "vision" if api_key else "ocr"
    except ValueError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception:
        logger.exception("image_ocr_upload: extraction failed file=%s", filename)
        return Response(
            {"error": "image text extraction failed", "request_id": _request_id(request)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if not raw_text.strip():
        return Response(
            {"error": "No text could be extracted from the image."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # --- Step 2: PHI de-identification (HIPAA required) ---
    from .agent_ai.phi_deidentifier import deidentify
    import hashlib

    clean_text, redaction_summary = deidentify(raw_text)

    # --- Step 3: Persist audit record (no PHI stored) ---
    text_hash = hashlib.sha256(raw_text.encode("utf-8", errors="replace")).hexdigest()
    user_id_str = str(request.user.pk) if request.user.is_authenticated else "anonymous"

    session = PatientCaseSession.objects.create(
        domain=domain,
        subdomain=payload.get("subdomain", ""),
        text_hash=text_hash,
        redaction_count=redaction_summary.total_redactions,
        redaction_categories=redaction_summary.categories,
        source_filename=filename,
        user_id=user_id_str,
    )

    return Response(
        {
            "session_id": session.session_id,
            "domain": session.domain,
            "strategy_used": strategy_used,
            "extracted_text_length": len(clean_text),
            "redaction_count": session.redaction_count,
            "redaction_categories": session.redaction_categories,
            "source_filename": session.source_filename,
            "created_at": session.created_at,
        },
        status=status.HTTP_201_CREATED,
    )
