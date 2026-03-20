import uuid
import time

from django.http import JsonResponse

from .request_context import reset_request_id, set_request_id
from .security import is_suspicious_payload, is_suspicious_user_agent, record_security_event
from .telemetry import incr, observe_latency_ms


class RequestIDMiddleware:
    """Attach a request id for tracing logs and responses."""

    header_name = "X-Request-ID"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get(self.header_name) or str(uuid.uuid4())
        request.request_id = request_id
        token = set_request_id(request_id)
        try:
            response = self.get_response(request)
            response[self.header_name] = request_id
            return response
        finally:
            reset_request_id(token)


class SecurityObservabilityMiddleware:
    """Capture latency/traffic metrics and block obvious abuse signatures."""

    MAX_CONTENT_LENGTH_BYTES = 10 * 1024 * 1024  # 10 MB hard limit at middleware layer.

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _client_ip(request) -> str | None:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR")

    def __call__(self, request):
        start = time.perf_counter()
        incr("http.requests.total")

        ip = self._client_ip(request)
        ua = request.META.get("HTTP_USER_AGENT", "")
        path = request.path
        method = request.method

        if is_suspicious_user_agent(ua):
            incr("security.blocks.total")
            record_security_event(
                event_type="suspicious_user_agent",
                severity=SecurityEventSeverity.HIGH,
                ip_address=ip,
                path=path,
                method=method,
                user_agent=ua,
                user=getattr(request, "user", None),
                meta={"reason": "known scanner signature in user-agent"},
            )
            return JsonResponse({"error": "request blocked", "detail": "suspicious client signature"}, status=403)

        content_length_header = request.META.get("CONTENT_LENGTH") or "0"
        try:
            content_length = int(content_length_header)
        except ValueError:
            content_length = 0
        if content_length > self.MAX_CONTENT_LENGTH_BYTES:
            incr("abuse.payload_oversize.total")
            incr("security.blocks.total")
            record_security_event(
                event_type="payload_oversize",
                severity=SecurityEventSeverity.MEDIUM,
                ip_address=ip,
                path=path,
                method=method,
                user_agent=ua,
                user=getattr(request, "user", None),
                meta={"content_length": content_length},
            )
            return JsonResponse({"error": "payload too large"}, status=413)

        suspicious_blob = f"{path}?{request.META.get('QUERY_STRING', '')}"
        if is_suspicious_payload(suspicious_blob):
            incr("abuse.suspicious_signature.total")
            incr("security.blocks.total")
            record_security_event(
                event_type="suspicious_signature",
                severity=SecurityEventSeverity.HIGH,
                ip_address=ip,
                path=path,
                method=method,
                user_agent=ua,
                user=getattr(request, "user", None),
                meta={"target": suspicious_blob[:300]},
            )
            return JsonResponse({"error": "request blocked"}, status=403)

        response = self.get_response(request)
        status_code = int(getattr(response, "status_code", 500))
        if 200 <= status_code < 300:
            incr("http.responses.2xx")
        elif 400 <= status_code < 500:
            incr("http.responses.4xx")
            if status_code in {401, 403}:
                incr("auth.failures.total")
        elif status_code >= 500:
            incr("http.responses.5xx")

        elapsed_ms = (time.perf_counter() - start) * 1000
        observe_latency_ms("latency.http", elapsed_ms)
        return response


class SecurityEventSeverity:
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
