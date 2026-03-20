import time
from collections.abc import Callable

from django.core.cache import cache


METRIC_PREFIX = "telemetry"
METRIC_TTL_SECONDS = 60 * 60 * 24 * 7


def _key(name: str) -> str:
    return f"{METRIC_PREFIX}:{name}"


def incr(name: str, amount: int = 1) -> None:
    k = _key(name)
    try:
        added = cache.add(k, 0, timeout=METRIC_TTL_SECONDS)
        if added:
            cache.set(k, amount, timeout=METRIC_TTL_SECONDS)
            return
        try:
            cache.incr(k, amount)
        except ValueError:
            cache.set(k, amount, timeout=METRIC_TTL_SECONDS)
    except Exception:
        return


def get(name: str, default: int = 0) -> int:
    try:
        value = cache.get(_key(name), default)
    except Exception:
        value = default
    return int(value or 0)


def observe_latency_ms(name: str, latency_ms: float) -> None:
    # Aggregate count + sum so average can be derived without external TSDB.
    incr(f"{name}:count", 1)
    incr(f"{name}:sum_ms", int(latency_ms))


def timed(operation_name: str, fn: Callable):
    start = time.perf_counter()
    result = fn()
    elapsed_ms = (time.perf_counter() - start) * 1000
    observe_latency_ms(operation_name, elapsed_ms)
    return result


def snapshot() -> dict:
    keys = [
        "http.requests.total",
        "http.responses.2xx",
        "http.responses.4xx",
        "http.responses.5xx",
        "security.events.total",
        "security.blocks.total",
        "auth.failures.total",
        "abuse.payload_oversize.total",
        "abuse.suspicious_signature.total",
        "billing.events.total",
        "billing.subscriptions.created",
        "billing.usage_events.total",
        "latency.http:count",
        "latency.http:sum_ms",
    ]
    data: dict[str, float] = {k: float(get(k, 0)) for k in keys}
    count = data.get("latency.http:count", 0)
    sum_ms = data.get("latency.http:sum_ms", 0)
    data["latency.http:avg_ms"] = round((sum_ms / count), 2) if count else 0.0
    return data


def prometheus_text() -> str:
    data = snapshot()
    lines = [
        "# HELP clinigraph_http_requests_total Total HTTP requests seen by the application",
        "# TYPE clinigraph_http_requests_total counter",
        f"clinigraph_http_requests_total {data.get('http.requests.total', 0)}",
        "# HELP clinigraph_http_responses_2xx Total successful HTTP responses",
        "# TYPE clinigraph_http_responses_2xx counter",
        f"clinigraph_http_responses_2xx {data.get('http.responses.2xx', 0)}",
        "# HELP clinigraph_http_responses_4xx Total client error HTTP responses",
        "# TYPE clinigraph_http_responses_4xx counter",
        f"clinigraph_http_responses_4xx {data.get('http.responses.4xx', 0)}",
        "# HELP clinigraph_http_responses_5xx Total server error HTTP responses",
        "# TYPE clinigraph_http_responses_5xx counter",
        f"clinigraph_http_responses_5xx {data.get('http.responses.5xx', 0)}",
        "# HELP clinigraph_security_events_total Total security events recorded",
        "# TYPE clinigraph_security_events_total counter",
        f"clinigraph_security_events_total {data.get('security.events.total', 0)}",
        "# HELP clinigraph_security_blocks_total Total blocked malicious or abusive requests",
        "# TYPE clinigraph_security_blocks_total counter",
        f"clinigraph_security_blocks_total {data.get('security.blocks.total', 0)}",
        "# HELP clinigraph_auth_failures_total Total authentication failures",
        "# TYPE clinigraph_auth_failures_total counter",
        f"clinigraph_auth_failures_total {data.get('auth.failures.total', 0)}",
        "# HELP clinigraph_billing_events_total Total billing events recorded",
        "# TYPE clinigraph_billing_events_total counter",
        f"clinigraph_billing_events_total {data.get('billing.events.total', 0)}",
        "# HELP clinigraph_billing_usage_events_total Total billing usage events ingested",
        "# TYPE clinigraph_billing_usage_events_total counter",
        f"clinigraph_billing_usage_events_total {data.get('billing.usage_events.total', 0)}",
        "# HELP clinigraph_http_latency_avg_ms Average HTTP request latency in milliseconds",
        "# TYPE clinigraph_http_latency_avg_ms gauge",
        f"clinigraph_http_latency_avg_ms {data.get('latency.http:avg_ms', 0.0)}",
    ]
    return "\n".join(lines) + "\n"
