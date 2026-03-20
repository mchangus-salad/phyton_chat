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

- AgentAI module docs: [clinigraph-ai/api/agent_ai/README.md](clinigraph-ai/api/agent_ai/README.md)
- Mermaid architecture and flow diagrams: [clinigraph-ai/api/agent_ai/MERMAID_DIAGRAMS.md](clinigraph-ai/api/agent_ai/MERMAID_DIAGRAMS.md)
- Product branding guide: [clinigraph-ai/BRANDING.md](clinigraph-ai/BRANDING.md)
- Technical renaming roadmap: [clinigraph-ai/RENAMING_PLAN.md](clinigraph-ai/RENAMING_PLAN.md)

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
