# AgentAI Architecture

This module implements an AgentAI pipeline with:

- LLM: GPT or Claude
- Embeddings: OpenAI or HuggingFace
- Vector DB: Pinecone or Weaviate
- Orchestration: LangChain
- Agents: LangGraph
- Cache: Redis
- Queue: Kafka

## Sandbox mode (no-cost local dev)

This project supports a local sandbox LLM mode with no external API calls:

- `AGENT_LLM_PROVIDER=mock` (or `sandbox`)
- `AGENT_LLM_MODEL=mock-local-v1`

In sandbox mode, `/api/v1/agent/query/` returns deterministic local responses built from retrieved context.
This lets the team develop and test end-to-end flows without paying for GPT/Claude during development.

## Environment variables

Set these before using the endpoint:

- AGENT_LLM_PROVIDER=gpt|claude|mock|sandbox
- AGENT_LLM_MODEL=<model name>
- OPENAI_API_KEY=<key>
- ANTHROPIC_API_KEY=<key>
- AGENT_EMBEDDINGS_PROVIDER=openai|huggingface|local
- AGENT_EMBEDDINGS_MODEL=<embedding model>
- AGENT_VECTOR_DB_PROVIDER=pinecone|weaviate
- PINECONE_API_KEY=<key>
- PINECONE_INDEX=<index>
- PINECONE_NAMESPACE=<namespace>
- WEAVIATE_URL=<cloud url>
- WEAVIATE_API_KEY=<key>
- WEAVIATE_INDEX=<index>
- REDIS_URL=redis://127.0.0.1:6379/0
- KAFKA_BOOTSTRAP_SERVERS=127.0.0.1:9094
- AGENT_KAFKA_TOPIC=agent-events

## Local Docker stack

The repository includes [docker-compose.local.yml](d:/study-python/chat-build/docker-compose.local.yml) for local infrastructure:

- Redis on 127.0.0.1:6379
- Kafka on 127.0.0.1:9094
- Kafka UI on http://127.0.0.1:8085
- Weaviate on http://127.0.0.1:8088

The file [.env.agentai.local](d:/study-python/chat-build/.env.agentai.local) is loaded automatically by the app and points to those local services.

Start local services with:

```powershell
docker compose -f docker-compose.local.yml up -d
```

## One-command developer setup

For a new developer on Windows, the easiest setup is:

```powershell
.\scripts\dev-up.ps1
```

Create or update a local JWT user:

```powershell
.\scripts\create-dev-user.ps1
.\scripts\create-dev-user.ps1 -Username agentadmin -Password "StrongPass123!" -Superuser
```

Run a quick end-to-end API check (health -> auth -> agent query):

```powershell
.\scripts\quick-test.ps1
.\scripts\quick-test.ps1 -UseApiKey
```

Run a local CI-style flow (bootstrap -> temporary server -> quick test -> cleanup):

```powershell
.\scripts\ci-local.ps1
.\scripts\ci-local.ps1 -UseApiKey -RunDevDown
.\scripts\ci-local.ps1 -SkipBootstrap -UseApiKey
```

What it does:

- creates `.venv`
- installs Python dependencies
- creates `.env.agentai.local` from the example if missing
- starts Redis, Kafka, Kafka UI, and Weaviate in Docker
- ensures Weaviate collection/schema exists
- runs Django migrations and checks
- runs a smoke test against `/api/health/`
- starts the Django development server on `127.0.0.1:8000`

Useful options:

```powershell
.\scripts\dev-up.ps1 -NoServer
.\scripts\dev-up.ps1 -RecreateVenv
.\scripts\dev-up.ps1 -SkipDocker
.\scripts\dev-up.ps1 -SkipSmokeTest
.\scripts\dev-up.ps1 -SkipSeed
```

Stop local stack with:

```powershell
.\scripts\dev-down.ps1
.\scripts\dev-down.ps1 -RemoveVolumes
```

Seed data manually (idempotent):

```powershell
.\scripts\dev-seed.ps1
```

By default, local environment uses deterministic offline embeddings (`AGENT_EMBEDDINGS_PROVIDER=local`) so seed and retrieval can run without external embedding APIs.

Stop local services with:

```powershell
docker compose -f docker-compose.local.yml down
```

Notes:

- GPT and Claude are not local services. You still need OPENAI_API_KEY or ANTHROPIC_API_KEY when provider is `gpt` or `claude`.
- Use `AGENT_LLM_PROVIDER=mock` for local sandbox without paid APIs.
- Pinecone is not self-hosted locally, so the local environment is configured to use Weaviate instead.

## API endpoint

Primary endpoint:

- POST /api/v1/agent/query/

Legacy compatibility endpoint:

- POST /api/agent/query/

Headers:

- Content-Type: application/json
- X-API-Key: <key>

Authentication options:

- Option 1: Send X-API-Key (the default local flow)
- Option 2: Send Authorization: Bearer <jwt-access-token>

JWT token endpoints:

- POST /api/v1/auth/token/
- POST /api/v1/auth/token/refresh/

OpenAPI and Swagger docs:

- GET /api/schema/
- GET /api/docs/

Body:

{
  "question": "What is our refund policy?",
  "user_id": "u-123"
}

Example token request:

{
  "username": "your-username",
  "password": "your-password"
}
