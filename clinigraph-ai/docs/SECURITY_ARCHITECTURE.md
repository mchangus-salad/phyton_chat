# CliniGraph AI — Security Architecture Document

## 1. Threat Model Overview

CliniGraph AI is a multi-tenant SaaS platform handling clinical decision support for healthcare professionals. Protected assets include:

| Asset | Classification | Controls |
|---|---|---|
| PHI submitted in patient-case analysis | HIPAA-regulated | Never persisted; de-identified before pipeline |
| Tenant clinical query history | Confidential (per tenant) | Scoped to tenant via RBAC |
| JWT credentials | Authentication material | Short-lived (15 min access), refresh rotation |
| API keys | Service authentication | SHA-256 hashed in DB, prefix-visible only |
| Security event log | Operational telemetry | Staff-only read, append-only writes |
| Billing data (Stripe) | PCI-adjacent | Stripe-held; local metadata only |

---

## 2. Authentication Architecture

### JWT (Primary)
- Issued by `CliniGraphTokenObtainPairView` (SimpleJWT override)
- Access token: **15-minute** TTL
- Refresh token: **7-day** TTL with **rotation** (each use issues new pair, old invalidated)
- Token blacklist: enabled via `rest_framework_simplejwt.token_blacklist`
- Custom claims: `tenant_memberships`, `roles`, `is_staff_user`
- Encoding: RS256 (production) / HS256 (dev)

### API Keys (Secondary)
- Used by server-to-server integrations and script clients
- Format: `cg_{40-char hex prefix}` — human-readable prefix stored, actual token hashed (SHA-256)
- Checked by `HasLlmAccessOrApiKey` and `HasAgentApiKeyOrAuthenticated` permission classes
- Rate-limited separately from user sessions

### Permission Classes (RBAC)
| Class | Description |
|---|---|
| `HasLlmAccessOrApiKey` | Requires valid JWT + LLM entitlement OR valid API key |
| `HasAgentApiKeyOrAuthenticated` | Authenticated user OR API key |
| `HasActiveEntitlement` | Checks active subscription + grace-period status |
| `IsTenantAdminOrOwner` | Tenant role ≥ admin |
| `IsTenantBillingAdminOrOwner` | Tenant role = billing, admin, or owner |
| `IsAuthenticated` (DRF) | Any valid JWT |

---

## 3. Multi-Tenant Data Isolation

Every tenant-scoped queryset uses `TenantBoundManager` — a custom Django manager that injects `tenant=<current_tenant>` filter for all queries. Raw querysets (`objects`) are reserved for admin/migration use only.

Isolation enforcement:
1. `X-Tenant-ID` header parsed and validated by middleware
2. `request.tenant` is set only when the calling user has a verified `TenantMembership`
3. `TenantBoundManager` filters at the ORM layer — cross-tenant leakage requires bypassing the manager (never done in application code)
4. Tests assert 403 when tenant mismatch is deliberately forced

---

## 4. PHI De-identification Pipeline (HIPAA)

Patient text submitted to `POST /api/v1/agent/patient/analyze/` flows through:

```
User text → phi_deidentifier.py → de-identified text → LangGraph pipeline → response
```

- **No PHI ever touches the database or log files**
- `PatientCaseSession` stores only: SHA-256 hash of original text (dedup), redaction category counters, domain label, user ID
- `phi_deidentifier.py` uses a combination of regex rules for HIPAA Safe Harbor categories (names, dates, phone numbers, geographic data, ages >89, etc.) and a spaCy NER model when available
- Redaction categories are auditable via `GET /api/v1/audit/patient-cases/` (staff-only)

---

## 5. Security Event Telemetry

Security events are written by `api/security.py` → `SecurityEvent` model for:
- Auth failures (invalid JWT, expired token, bad API key)
- Rate-limit blocks
- Oversized payloads
- Suspicious patterns (header anomalies, path traversal attempts)
- Role escalation attempts

Events are viewable by staff at:
- `GET /api/v1/security/events/recent/?limit=N` — JSON, last N events
- `GET /api/v1/security/events/export/?format=json|cef&limit=N` — SIEM-ready export

CEF export format: ArcSight Common Event Format v0 compatible — suitable for Splunk, QRadar, Microsoft Sentinel ingestion.

---

## 6. SIEM Integration Guide

### NDJSON Export
```bash
curl -H "Authorization: Bearer <staff_token>" \
     "https://api.clinigraph.ai/api/v1/security/events/export/?format=json&limit=1000" \
  | filebeat -ingest_pipeline clinigraph_security
```

### CEF Export (Splunk / QRadar)
```bash
curl -H "Authorization: Bearer <staff_token>" \
     "https://api.clinigraph.ai/api/v1/security/events/export/?format=cef&limit=1000" \
  | nc siem-host 514
```

CEF severity mapping:
| Severity | CEF Level |
|---|---|
| critical | 10 |
| high | 8 |
| medium | 5 |
| low | 3 |

---

## 7. Network Security Baseline

| Control | Status | Notes |
|---|---|---|
| HTTPS enforcement | ✅ | `SECURE_SSL_REDIRECT=True` in production |
| HSTS | ✅ | `SECURE_HSTS_SECONDS=31536000` + preload |
| X-Content-Type-Options | ✅ | `SECURE_CONTENT_TYPE_NOSNIFF=True` |
| XSS protection header | ✅ | `SECURE_BROWSER_XSS_FILTER=True` |
| Clickjacking protection | ✅ | `X_FRAME_OPTIONS=DENY` |
| CSRF | ✅ | Django CSRF middleware active |
| CORS | ✅ | `CORS_ALLOWED_ORIGINS` explicit allowlist |
| Secure cookies | ✅ | `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` |
| Rate limiting | ✅ | Anon: 30/min, User: 120/min, Agent: separate class |

---

## 8. Secrets Management

| Secret | Storage | Rotation |
|---|---|---|
| Django `SECRET_KEY` | Environment variable | Rotate at deploy; old sessions invalidated |
| `OPENAI_API_KEY` | Environment variable | Rotate quarterly or on compromise |
| `ANTHROPIC_API_KEY` | Environment variable | Rotate quarterly or on compromise |
| `STRIPE_SECRET_KEY` | Environment variable | Rotate on compromise; Stripe webhook secret separate |
| `BILLING_WEBHOOK_SECRET` | Environment variable | Rotate when Stripe endpoint changes |
| DB password | Environment variable / secrets manager | Rotate annually or on compromise |
| Redis password | Environment variable | Rotate annually |

**Rotation runbook**: Use `scripts/rotate-secrets.ps1` (to be created) — invalidates JWT blacklist, rotates key, restarts services.

---

## 9. Remaining Security Roadmap Items

| Item | Priority | Notes |
|---|---|---|
| SIEM export pipeline | ✅ Done | `/security/events/export/` endpoint |
| Geo/IP reputation controls | Medium | Integrate MaxMind GeoIP; block known-bad ASNs |
| WAF / reverse proxy hardening | Medium | Nginx ModSecurity ruleset or Cloudflare WAF |
| Penetration testing checklist | High | OWASP WSTG checklist + annual red-team |
| Secrets rotation runbook | High | Documented procedure + script |
