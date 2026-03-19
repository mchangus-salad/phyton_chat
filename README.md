# CliniGraph AI

Clinical Evidence Intelligence Platform

Legacy workspace codename: chat-build (renamed to clinigraph-ai)

## What The Program Does Today

This repository currently includes the CliniGraph AI backend, a Django-based AgentAI platform focused on RAG workflows and medical research support.

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
