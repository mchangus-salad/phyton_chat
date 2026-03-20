# CliniGraph AI - Client Usage Manual (English)

This is the official living manual for client operations in English.

Policy:

- Update this file whenever endpoints, workflows, security controls, or deployment procedures change.
- Keep this file aligned with [CLIENT_MANUAL.md](CLIENT_MANUAL.md).

## 1. Platform Purpose

CliniGraph AI helps clinical teams:

- Upload or submit de-identified patient case information.
- Query evidence-based medical knowledge by specialty.
- Retrieve structured citations and supporting evidence.
- Keep the clinical corpus updated via scheduled PubMed ingestion.

## 2. Security and Compliance

### HIPAA handling in patient-case workflow

Patient-case analysis applies automatic PHI de-identification before any AI inference.

Current controls:

1. Extract raw text from payload (text or file).
2. Detect and redact PHI categories (Safe Harbor patterns).
3. Build prompts only from de-identified content.
4. Return analysis plus redaction summary.
5. Persist audit metadata only. Raw PHI text is not stored.

Important note:

- Automated de-identification is best-effort and should be complemented by organizational compliance controls and human review where required.

## 3. Core API Flows

### 3.1 Patient case analysis

Endpoint:

- POST /api/v1/agent/patient/analyze/

Accepted payload:

- text (optional): free-text history/symptoms/labs.
- file (optional): .txt, .pdf, .docx, .csv, .json.
- domain (optional): cardiology, neurology, oncology, etc.
- subdomain (optional): specialty focus.
- question (optional): targeted clinical question.
- user_id (optional): requesting user identifier.

Response fields:

- session_id
- analysis
- citations
- redaction_summary
- domain
- safety_notice
- request_id

### 3.2 Medical evidence query

Core endpoints:

- POST /api/v1/agent/medical/query/
- POST /api/v1/agent/medical/evidence/

Recommended usage:

- Use query endpoint for narrative responses.
- Use evidence endpoint for structured citations and filters.

### 3.3 Domain ingestion and uploads

Core endpoints:

- POST /api/v1/agent/medical/train/
- POST /api/v1/agent/medical/upload/
- POST /api/v1/agent/oncology/train/
- POST /api/v1/agent/oncology/upload/

## 4. SaaS Operations

### 4.1 Start stack

PowerShell:

```powershell
.\scripts\saas-up.ps1 -Seed
```

Services started:

- web API
- postgres
- redis
- kafka
- weaviate
- corpus-updater

### 4.2 Automated corpus updater

The updater periodically refreshes domain knowledge from PubMed.

Required configuration:

- CORPUS_UPDATE_INTERVAL_HOURS
- NCBI_API_KEY

## 5. Authentication

Options:

- JWT bearer token.
- X-API-Key.

Token endpoints:

- POST /api/v1/auth/token/
- POST /api/v1/auth/token/refresh/

## 6. Roles and Access

The platform uses tenant-scoped roles through `TenantMembership`.

Available roles:

1. `owner`
2. `admin`
3. `billing`
4. `clinician`
5. `auditor`

Access matrix (summary):

1. `owner`: full tenant control, billing control, and administrative operations.
2. `admin`: tenant administration and billing operations based on endpoint policy.
3. `billing`: billing management (portal, invoices, usage summary) with no LLM endpoint access.
4. `clinician`: clinical/LLM workflows (query, evidence, patient analyze).
5. `auditor`: audit-oriented role; no automatic LLM or restricted billing privileges.

Key policy:

1. `billing` users are blocked from LLM endpoints (`/api/v1/agent/*`).
2. `billing` users can still manage billing and payment recovery workflows.
3. Entitlement enforcement may return HTTP 402 for service-protected endpoints.

### 6.1 Tenant User, Role, and Access Administration

The platform now includes tenant membership administration endpoints.

Endpoints:

1. `GET /api/v1/tenants/memberships/` list tenant memberships.
2. `POST /api/v1/tenants/memberships/create/` create or attach a user to tenant with a role.
3. `PATCH /api/v1/tenants/memberships/{membership_id}/` update role or active/inactive state.

Permissions:

1. Only `owner` and `admin` can call these endpoints.
2. `billing`, `clinician`, and `auditor` receive `403`.
3. Safety rule: the API prevents removing/demoting the last active `owner` in a tenant.

Frontend screen (React):

1. New "Tenant users, roles, and access" section in the web dashboard.
2. Supports member listing, user create/attach, role change, and activate/deactivate actions.
3. Requires `JWT` and `X-Tenant-ID` for the target tenant.

Operational permissions matrix (tenant memberships):

| Action | owner | admin | billing | clinician | auditor |
|--------|-------|-------|---------|-----------|---------|
| View access-management screen | Yes | Yes | No | No | No |
| List memberships (`GET /tenants/memberships/`) | Yes | Yes | No (403) | No (403) | No (403) |
| Create/attach user (`POST /tenants/memberships/create/`) | Yes | Yes | No (403) | No (403) | No (403) |
| Change another member role (`PATCH /tenants/memberships/{id}/`) | Yes | Yes | No (403) | No (403) | No (403) |
| Activate/deactivate membership (`PATCH /tenants/memberships/{id}/`) | Yes | Yes | No (403) | No (403) | No (403) |
| Demote/deactivate last active owner | No (400) | No (400) | No | No | No |

QA/Support notes:

1. For `billing` users, all membership admin endpoints must return `403`.
2. Expected error when trying to remove the last active owner is `400` with `cannot remove last owner`.
3. Validate requests with `Authorization: Bearer <jwt>` and `X-Tenant-ID` headers.

## 7. Health and Support Checks

Health endpoint:

- GET /api/v1/health/

OpenAPI docs:

- GET /api/docs/

Operational checklist:

1. Verify health endpoint returns status ok.
2. Validate auth flow.
3. Run a medical query and confirm citations are returned.
4. Run a patient-case analysis and review redaction summary.

## 8. Diagrams

Detailed architecture and flow diagrams are maintained in:

- [MERMAID_DIAGRAMS.md](MERMAID_DIAGRAMS.md)

## 9. Maintenance Workflow

For every feature change, update:

1. [README.md](../README.md)
2. [AGENT_AI_README.md](AGENT_AI_README.md)
3. [MERMAID_DIAGRAMS.md](MERMAID_DIAGRAMS.md)
4. [CLIENT_MANUAL.md](CLIENT_MANUAL.md)
5. [CLIENT_MANUAL_EN.md](CLIENT_MANUAL_EN.md)

Template:

- [DOC_UPDATE_TEMPLATE.md](DOC_UPDATE_TEMPLATE.md)
- [PLATFORM_ROADMAP.md](PLATFORM_ROADMAP.md)

## 10. Document Version History

| Version | Date       | Change Summary                                                            | Affected Endpoints                                | Client Action Required |
|---------|------------|---------------------------------------------------------------------------|---------------------------------------------------|------------------------|
| 1.0.0   | 2026-03-20 | Initial EN client manual aligned to ES manual                             | `/api/v1/agent/*`, `/api/v1/health/`, `/api/docs/` | No                     |
| 1.1.0   | 2026-03-20 | Added tenant role matrix and billing-role access policy                  | `/api/v1/agent/*`, `/api/v1/billing/*`           | No                     |
| 1.2.0   | 2026-03-20 | Added tenant user/role administration endpoints and frontend access-management screen | `/api/v1/tenants/memberships/*`                  | No                     |
