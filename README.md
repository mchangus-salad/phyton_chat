# phyton_chat

## What The Program Does Today

This repository currently includes a Django-based AgentAI backend focused on RAG workflows and oncology research support.

Implemented so far:

- Versioned REST API (`/api/v1`) with health, auth, agent query, oncology ingestion, oncology query, and oncology evidence endpoints.
- Security and operations features including JWT auth, optional API key auth, throttling, request ID middleware, and OpenAPI/Swagger documentation.
- Pluggable AI stack: LLM provider, embeddings provider, vector database provider, cache, and event queue.
- Oncology corpus ingestion from JSON payloads, file uploads, and bulk import commands/scripts.
- Metadata-aware retrieval with filters and structured evidence responses including citations and scores.
- Local no-cost developer mode and reproducible Docker services for Redis, Kafka, and Weaviate.

## Documentation

- AgentAI module docs: [chat-build/api/agent_ai/README.md](chat-build/api/agent_ai/README.md)
- Mermaid architecture and flow diagrams: [chat-build/api/agent_ai/MERMAID_DIAGRAMS.md](chat-build/api/agent_ai/MERMAID_DIAGRAMS.md)
