# CliniGraph AI - Client Usage Manual

This is the official living manual for client operations.

Policy for this file:

- This document must be updated whenever endpoints, flows, security controls, or deployment steps change.
- Product and operations teams should treat this file as the primary customer-facing runbook.

## 1. Platform Purpose

CliniGraph AI helps clinicians and medical teams:

- Upload or submit de-identified patient case information.
- Query evidence-based medical knowledge by specialty.
- Retrieve structured citations and supporting evidence.
- Keep the clinical corpus updated with scheduled PubMed ingestion.

## 2. Security and Compliance

### HIPAA handling in patient-case flow

Patient-case analysis applies automatic PHI de-identification before any AI inference.

Current controls:

1. Extract raw text from request payload (text or file).
2. Detect and redact PHI categories (Safe Harbor pattern set).
3. Build model prompt from de-identified content only.
4. Return analysis and redaction summary.
5. Persist audit metadata only. Raw PHI text is not stored.

Important note:

- Automated de-identification is best-effort and must be complemented by organizational compliance controls and human review where required.

## 3. Main API Flows

### 3.1 Patient case analysis

Endpoint:

- POST /api/v1/agent/patient/analyze/

Accepted payload:

- text (optional): free-text history/symptoms/labs.
- file (optional): .txt, .pdf, .docx, .csv, .json.
- domain (optional): cardiology, neurology, oncology, etc.
- subdomain (optional): focused specialty segment.
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

```mermaid
flowchart TD
    A[Doctor Uploads Text or File] --> B[Text Extraction]
    B --> C[HIPAA Safe Harbor De-identification]
    C --> D{PHI Found?}
    D -->|Yes| E[Replace with Redaction Tokens]
    D -->|No| F[Pass-through De-identified Text]
    E --> G[Build Clinical Prompt]
    F --> G
    G --> H[Domain Retrieval in Vector DB]
    H --> I[LLM Clinical Analysis]
    I --> J[Return Analysis with Citations]
    J --> K[Store Audit Metadata Only]
    K --> L[Client Receives Session ID + Redaction Summary]
```

Interpretation:

- De-identification always happens before prompt generation.
- The response includes both analysis and traceability metadata.

### 3.2 Medical evidence query

Core endpoints:

- POST /api/v1/agent/medical/query/
- POST /api/v1/agent/medical/evidence/

Recommended use:

- Use query endpoint for narrative answers.
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

This starts:

- web API
- postgres
- redis
- kafka
- weaviate
- corpus-updater

### 4.2 Automated corpus updater

The updater periodically refreshes domain knowledge from PubMed.

```mermaid
sequenceDiagram
    autonumber
    participant Scheduler as corpus-updater
    participant Django as auto_update_corpus
    participant NCBI as PubMed E-utilities
    participant State as corpus_state.json
    participant Ingest as CliniGraphService
    participant Vector as Weaviate

    Scheduler->>Django: Run every N hours
    Django->>State: Load seen PMIDs
    Django->>NCBI: esearch by topic and days-back
    NCBI-->>Django: PMIDs
    Django->>NCBI: efetch MEDLINE records
    NCBI-->>Django: title/abstract/metadata
    Django->>Django: Parse + infer evidence type
    Django->>State: Skip existing PMIDs and save new state
    Django->>Ingest: ingest_documents by domain/subdomain
    Ingest->>Vector: Upsert vectors and metadata
    Vector-->>Ingest: Indexed counts
    Ingest-->>Django: Ingestion result summary
```

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

## 6. Roles y Accesos

La plataforma usa roles por tenant (organizacion) via `TenantMembership`.

Roles disponibles:

1. `owner`
2. `admin`
3. `billing`
4. `clinician`
5. `auditor`

Matriz de acceso resumida:

1. `owner`: control total de tenant, billing y operaciones administrativas.
2. `admin`: operaciones administrativas de tenant y billing segun endpoint.
3. `billing`: gestion de facturacion (portal, invoices, resumen) pero sin acceso a endpoints LLM.
4. `clinician`: uso de flujos clinicos/LLM (query, evidence, patient analyze).
5. `auditor`: rol de auditoria; no implica acceso automatico a LLM ni acciones de billing restringidas.

Politica clave:

1. El rol `billing` no puede usar endpoints LLM (`/api/v1/agent/*`).
2. El rol `billing` si puede gestionar billing y recuperacion de pago.
3. El control de entitlement puede bloquear endpoints de servicio con HTTP 402 cuando aplica.

### 6.1 Administracion de usuarios, roles y accessos por tenant

La plataforma incluye endpoints para administrar usuarios del tenant y sus roles.

Endpoints:

1. `GET /api/v1/tenants/memberships/` lista membresias del tenant.
2. `POST /api/v1/tenants/memberships/create/` crea o asocia un usuario al tenant con rol.
3. `PATCH /api/v1/tenants/memberships/{membership_id}/` actualiza rol o estado activo/inactivo.

Permisos:

1. Solo `owner` y `admin` pueden invocar estos endpoints.
2. `billing`, `clinician` y `auditor` reciben `403`.
3. Regla de seguridad: no se permite remover/degradar al ultimo `owner` activo del tenant.

Pantalla cliente (React):

1. Dashboard de "Tenant users, roles, and access" integrado en la app web.
2. Permite listar miembros, crear/asociar usuario y cambiar rol/estado.
3. Requiere `JWT` y `X-Tenant-ID` del tenant objetivo.

Matriz operativa de permisos (tenant memberships):

| Accion | owner | admin | billing | clinician | auditor |
|--------|-------|-------|---------|-----------|---------|
| Ver pantalla de administracion de accesos | Si | Si | No | No | No |
| Listar membresias (`GET /tenants/memberships/`) | Si | Si | No (403) | No (403) | No (403) |
| Crear/asociar usuario (`POST /tenants/memberships/create/`) | Si | Si | No (403) | No (403) | No (403) |
| Cambiar rol de otro miembro (`PATCH /tenants/memberships/{id}/`) | Si | Si | No (403) | No (403) | No (403) |
| Activar/desactivar membresia (`PATCH /tenants/memberships/{id}/`) | Si | Si | No (403) | No (403) | No (403) |
| Degradar/desactivar ultimo owner activo | No (400) | No (400) | No | No | No |

Notas para QA/Soporte:

1. Si un usuario tiene rol `billing`, la API debe devolver `403` en todos los endpoints de memberships.
2. El error esperado al intentar remover el ultimo owner activo es `400` con mensaje `cannot remove last owner`.
3. Validar siempre requests con `Authorization: Bearer <jwt>` y header `X-Tenant-ID`.

```mermaid
flowchart LR
    A[Usuario con rol billing] --> B[Endpoints de Billing]
    B --> C[Permitido]

    A --> D[Endpoints LLM /api/v1/agent/*]
    D --> E[403 Forbidden]

    F[Owner/Admin/Clinician] --> D
    D --> G[Permitido segun politica y auth]
```

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

## 8. End-user Operational Diagram

```mermaid
flowchart LR
    A[Cliente Clinica] --> B[Autenticacion JWT o API Key]
    B --> C[Subir Caso de Paciente]
    C --> D[Respuesta de Analisis + Citas]

    A --> E[Entrenar Corpus Medico]
    E --> F[Busqueda de Evidencia]

    A --> G[Monitorear Salud API]
    G --> H[Endpoint Health]

    I[Equipo TI] --> J[saas-up.ps1 -Seed]
    J --> K[Docker Compose SaaS]
    K --> L[Web + Postgres + Redis + Kafka + Weaviate + corpus-updater]
```

## 9. Change Log Policy for This Manual

Each future update should include:

- date
- feature changed
- affected endpoint(s)
- migration or deployment impact
- client action required

## 10. Documentation Maintenance Workflow

For every new feature or modification, update these docs together:

1. [README.md](../README.md) (global summary and links).
2. [AGENT_AI_README.md](AGENT_AI_README.md) (technical implementation details).
3. [MERMAID_DIAGRAMS.md](MERMAID_DIAGRAMS.md) (architecture and flow diagrams).
4. This client manual in Spanish: [CLIENT_MANUAL.md](CLIENT_MANUAL.md).
5. Client manual in English: [CLIENT_MANUAL_EN.md](CLIENT_MANUAL_EN.md).

Use the standard template:

- [DOC_UPDATE_TEMPLATE.md](DOC_UPDATE_TEMPLATE.md)
- [PLATFORM_ROADMAP.md](PLATFORM_ROADMAP.md)

## 11. Document Version History

| Version | Date       | Change Summary                                                                 | Affected Endpoints                                | Client Action Required |
|---------|------------|--------------------------------------------------------------------------------|---------------------------------------------------|------------------------|
| 1.0.0   | 2026-03-20 | Initial client manual with API, SaaS operations, HIPAA case flow, and diagrams | `/api/v1/agent/*`, `/api/v1/health/`, `/api/docs/` | No                     |
| 1.1.0   | 2026-03-20 | Added living-document policy, bilingual documentation links, and update workflow | Documentation only                                | No                     |
| 1.2.0   | 2026-03-20 | Added tenant role matrix and billing-role access policy                         | `/api/v1/agent/*`, `/api/v1/billing/*`           | No                     |
| 1.3.0   | 2026-03-20 | Added tenant user/role administration endpoints and frontend access-management screen | `/api/v1/tenants/memberships/*`                  | No                     |
