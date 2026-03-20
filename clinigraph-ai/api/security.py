import re

from .models import SecurityEvent
from .telemetry import incr


_SUSPICIOUS_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"union\s+select",
        r"drop\s+table",
        r"or\s+1=1",
        r"<script",
        r"\.\./",
        r"/etc/passwd",
        r"xp_cmdshell",
        r"information_schema",
    ]
]


_BAD_USER_AGENTS = [
    "sqlmap",
    "nikto",
    "nmap",
    "masscan",
    "acunetix",
    "dirbuster",
    "hydra",
]


def is_suspicious_payload(raw: str) -> bool:
    return any(pattern.search(raw or "") for pattern in _SUSPICIOUS_PATTERNS)


def is_suspicious_user_agent(user_agent: str) -> bool:
    ua = (user_agent or "").lower()
    return any(sig in ua for sig in _BAD_USER_AGENTS)


def record_security_event(
    *,
    event_type: str,
    severity: str,
    ip_address: str | None,
    path: str,
    method: str,
    user_agent: str,
    user,
    meta: dict | None = None,
) -> None:
    incr("security.events.total")
    SecurityEvent.objects.create(
        event_type=event_type,
        severity=severity,
        ip_address=ip_address,
        path=(path or "")[:255],
        method=(method or "")[:12],
        user_agent=(user_agent or "")[:512],
        user=user if getattr(user, "is_authenticated", False) else None,
        meta=meta or {},
    )
