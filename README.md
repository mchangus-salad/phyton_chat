# CliniGraph AI

Clinical Evidence Intelligence Platform

Workspace directory: clinigraph-ai

## What The Program Does Today

This repository currently includes the CliniGraph AI backend, a Django-based platform focused on RAG workflows and medical research support.

Implemented so far:

- Versioned REST API (`/api/v1`) with health, auth, agent query, oncology ingestion, oncology query, and oncology evidence endpoints.
- Security and operations features including JWT auth, optional API key auth, throttling, request ID middleware, and OpenAPI/Swagger documentation.
- Pluggable AI stack: LLM provider, embeddings provider, vector database provider, cache, and event queue.
- Oncology corpus ingestion from JSON payloads, file uploads, and bulk import commands/scripts.
- Metadata-aware retrieval with filters and structured evidence responses including citations and scores.
- Local no-cost developer mode and reproducible Docker services for Redis, Kafka, and Weaviate.

## Documentation

- Documentation hub: [clinigraph-ai/docs/README.md](clinigraph-ai/docs/README.md)
- AgentAI module docs: [clinigraph-ai/docs/AGENT_AI_README.md](clinigraph-ai/docs/AGENT_AI_README.md)
- Mermaid architecture and flow diagrams: [clinigraph-ai/docs/MERMAID_DIAGRAMS.md](clinigraph-ai/docs/MERMAID_DIAGRAMS.md)
- Client usage manual (living document): [clinigraph-ai/docs/CLIENT_MANUAL.md](clinigraph-ai/docs/CLIENT_MANUAL.md)
- Client usage manual (English): [clinigraph-ai/docs/CLIENT_MANUAL_EN.md](clinigraph-ai/docs/CLIENT_MANUAL_EN.md)
- Platform roadmap: [clinigraph-ai/docs/PLATFORM_ROADMAP.md](clinigraph-ai/docs/PLATFORM_ROADMAP.md)
- Documentation update template: [clinigraph-ai/docs/DOC_UPDATE_TEMPLATE.md](clinigraph-ai/docs/DOC_UPDATE_TEMPLATE.md)
- Product branding guide: [clinigraph-ai/docs/BRANDING.md](clinigraph-ai/docs/BRANDING.md)
- Technical renaming roadmap: [clinigraph-ai/docs/RENAMING_PLAN.md](clinigraph-ai/docs/RENAMING_PLAN.md)

## New Clinical Flow: Patient Case Analysis With HIPAA De-identification

The platform now supports case-level clinical analysis for patient notes and uploads.

Endpoint:

- POST `/api/v1/agent/patient/analyze/`

Input:

- `text` (free text), or
- `file` (`.txt`, `.pdf`, `.docx`, `.csv`, `.json`)
- optional `domain`, `subdomain`, `question`, `user_id`

What the backend does:

1. Extracts text from the uploaded payload.
2. Redacts PHI with HIPAA Safe Harbor rules before LLM processing.
3. Builds a structured clinical prompt from de-identified content.
4. Retrieves evidence from the domain knowledge base.
5. Returns analysis with citations and redaction summary.
6. Stores only audit metadata (no raw PHI text persisted).

See full examples and operational rules in [clinigraph-ai/docs/CLIENT_MANUAL.md](clinigraph-ai/docs/CLIENT_MANUAL.md).

## New Operational Flow: Automatic Medical Corpus Updates

The SaaS deployment now includes an automated updater service:

- `corpus-updater` calls `manage.py auto_update_corpus`
- Fetches fresh PubMed evidence by domain topics
- Deduplicates by persistent PMID state file
- Ingests new evidence into the vector index

Key environment variables:

- `CORPUS_UPDATE_INTERVAL_HOURS`
- `NCBI_API_KEY`

## SaaS Container Deployment

CliniGraph AI can run fully containerized for SaaS-style deployment.

1. Go to [clinigraph-ai](clinigraph-ai).
2. Run the idempotent installer:

```powershell
.\scripts\saas-up.ps1
```

3. If you need custom ports or secrets, edit `.env.saas.local` and run the installer again.
4. Start the stack manually if needed:

```powershell
docker compose -f docker-compose.saas.yml --env-file .env.saas.local up -d --build
```

5. Verify health:

```powershell
curl http://127.0.0.1:18000/api/v1/health/
```

6. Clean all runtime artifacts:

```powershell
.\scripts\saas-down.ps1
```

7. Refresh the running stack without full cleanup:

```powershell
.\scripts\saas-refresh.ps1
```
