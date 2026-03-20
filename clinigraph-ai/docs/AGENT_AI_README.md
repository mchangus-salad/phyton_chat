# CliniGraph AI Architecture

## Product Identity

- Product name: CliniGraph AI
- Category: Clinical Evidence Intelligence Platform
- Repository codename: clinigraph-ai

This module implements the CliniGraph AI pipeline with:

- LLM: GPT, Claude, or Ollama (local)
- Embeddings: OpenAI or HuggingFace
- Vector DB: Pinecone or Weaviate
- Orchestration: LangChain
- Agents: LangGraph
- Cache: Redis
- Queue: Kafka

## What This Program Does Today

At this stage, the program provides a production-oriented Django + DRF API for retrieval-augmented answers and oncology-focused research support.

Current capabilities:

- Runs a configurable AgentAI stack with pluggable LLM, embeddings, and vector database providers.
- Exposes secure API endpoints with JWT bearer auth and API key support.
- Supports general agent Q&A (`/api/v1/agent/query/`) with caching and request tracing.
- Supports oncology corpus ingestion by JSON payload, multipart upload, or management command import.
- Supports oncology evidence search with metadata filters (`subdomain`, `cancer_type`, `biomarker`, `evidence_type`, publication year range).
- Supports ingestion controls for deduplication and versioning (`upsert`, `batch-dedup`, `versioned`, `version_tag`).
- Supports optional reranking and structured evidence outputs with citation IDs, labels, and scores.
- Includes local reproducible infrastructure (Redis, Kafka, Weaviate) with automation scripts for setup, testing, and CI-like smoke flows.

## Mermaid Diagrams

Detailed diagrams for architecture, execution flow, request lifecycle, and data movement are available here:

- [CliniGraph AI Mermaid Diagrams](./MERMAID_DIAGRAMS.md)

Client-facing documentation:

- [Client Manual (Spanish)](./CLIENT_MANUAL.md)
- [Client Manual (English)](./CLIENT_MANUAL_EN.md)
- [Platform Roadmap](./PLATFORM_ROADMAP.md)
- [Documentation Update Template](./DOC_UPDATE_TEMPLATE.md)

## Sandbox mode (no-cost local dev)

This project supports a local sandbox LLM mode with no external API calls:

- `AGENT_LLM_PROVIDER=mock` (or `sandbox`)
- `AGENT_LLM_MODEL=mock-local-v1`

In sandbox mode, `/api/v1/agent/query/` returns deterministic local responses built from retrieved context.
This lets the team develop and test end-to-end flows without paying for GPT/Claude during development.

## Environment variables

Set these before using the endpoint:

- AGENT_LLM_PROVIDER=gpt|claude|ollama|mock|sandbox
- AGENT_LLM_MODEL=<model name>
- OPENAI_API_KEY=<key>
- ANTHROPIC_API_KEY=<key>
- OLLAMA_BASE_URL=http://127.0.0.1:11434
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

The repository includes [docker-compose.local.yml](d:/study-python/clinigraph-ai/docker-compose.local.yml) for local infrastructure:

- Redis on 127.0.0.1:6379
- Kafka on 127.0.0.1:9094
- Kafka UI on http://127.0.0.1:8085
- Weaviate on http://127.0.0.1:8088

The file [.env.agentai.local](d:/study-python/clinigraph-ai/.env.agentai.local) is loaded automatically by the app and points to those local services.

Start local services with:

```powershell
docker compose -f docker-compose.local.yml up -d
```

## SaaS Container Stack

For a full containerized runtime (web app + Postgres + Redis + Kafka + Weaviate), use:

```powershell
.\scripts\saas-up.ps1
```

The script is idempotent: it creates `.env.saas.local` if missing, generates application secrets when placeholders are still present, builds the image, starts the stack, and waits for `/api/v1/health/` to return `ok`.

Manual compose remains available:

```powershell
docker compose -f docker-compose.saas.yml --env-file .env.saas.local up -d --build
```

Recommended setup:

1. Copy `.env.saas.example` to `.env.saas.local`
2. Set production-grade secrets (`DJANGO_SECRET_KEY`, `AGENT_API_KEY`, database password)
3. Set `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS` for your domain
4. Ensure Ollama is reachable (for local models) via `OLLAMA_BASE_URL`
5. If host ports are already used, adjust external port vars: `WEB_EXTERNAL_PORT`, `POSTGRES_EXTERNAL_PORT`, `REDIS_EXTERNAL_PORT`, `KAFKA_EXTERNAL_PORT`, `WEAVIATE_HTTP_EXTERNAL_PORT`, `WEAVIATE_GRPC_EXTERNAL_PORT`

Health check endpoint:

- GET /api/v1/health/

Cleanup script:

```powershell
.\scripts\saas-down.ps1
```

By default it removes containers, networks, named volumes, the local built image, and `.env.saas.local`. Use switches like `-KeepVolumes`, `-KeepImage`, or `-KeepEnvFile` when you want a softer shutdown.

Refresh script:

```powershell
.\scripts\saas-refresh.ps1
```

Use it for quick updates without deleting volumes or the local environment file. It supports `-Pull` to fetch newer remote images, `-NoBuild` to skip rebuilding the web image, and `-RestartOnly` when you only need a controlled restart plus health validation.

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

Run an Ollama + oncology real smoke flow (health -> import -> evidence -> oncology query):

```powershell
.\scripts\smoke-ollama-oncology.ps1
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
- Ollama can run fully local models (for example, `llama3.1:8b`) when provider is `ollama`.
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

## V2 Generic Medical Endpoints

Version 2 adds generic disease-domain endpoints so the same platform can be used beyond oncology.

V2 endpoints:

- POST /api/v1/agent/medical/train/
- POST /api/v1/agent/medical/upload/
- POST /api/v1/agent/medical/query/
- POST /api/v1/agent/medical/evidence/

Generic import command:

- .venv\Scripts\python.exe manage.py import_medical_corpus <path-to-file>

Generic import helper script:

- .\scripts\import-medical.ps1

V2 sample dataset:

- .\data\medical_sample_cardiology.json

V2 real smoke test script (Ollama + medical endpoints):

- .\scripts\smoke-ollama-medical.ps1

V2 metadata supports both generic and oncology-compatible fields:

- Generic: `domain`, `condition`, `marker`, `markers`
- Oncology-compatible: `cancer_type`, `biomarker`, `biomarkers`

Migration note:

- Existing oncology endpoints remain available and backward compatible.
- New use cases should prefer the `/agent/medical/*` endpoints for non-oncology domains.

Example V2 medical train request:

{
  "domain": "cardiology",
  "subdomain": "heart-failure",
  "corpus_name": "cardiology-research",
  "documents": [
    {
      "source": "cardio-guideline-001",
      "title": "Heart failure biomarker guidance",
      "text": "Heart failure research frequently uses NT-proBNP to support risk stratification.",
      "condition": "heart failure",
      "markers": ["NT-proBNP", "BNP"],
      "evidence_type": "guideline",
      "publication_year": 2024
    }
  ]
}

Example V2 medical evidence request:

{
  "domain": "cardiology",
  "subdomain": "heart-failure",
  "query": "heart failure marker evidence",
  "condition": "heart failure",
  "marker": "NT-proBNP",
  "evidence_type": "guideline",
  "publication_year_from": 2020,
  "publication_year_to": 2026,
  "rerank": true,
  "max_results": 3
}

Example V2 helper commands:

```powershell
.\scripts\import-medical.ps1
.\scripts\import-medical.ps1 -Domain cardiology -Subdomain heart-failure -Path .\data\medical_sample_cardiology.json
.\scripts\smoke-ollama-medical.ps1
```

## Oncology knowledge training

This project can ingest an oncology-specific knowledge corpus into the vector store and then query it through a dedicated endpoint.

Training endpoint:

- POST /api/v1/agent/oncology/train/

Multipart upload endpoint:

- POST /api/v1/agent/oncology/upload/

Research query endpoint:

- POST /api/v1/agent/oncology/query/

Structured evidence endpoint:

- POST /api/v1/agent/oncology/evidence/

Bulk import command:

- .venv\Scripts\python.exe manage.py import_oncology_corpus <path-to-file>

Bulk import helper script:

- .\scripts\import-oncology.ps1

Sample corpus file:

- .\data\oncology_sample.json

Example training request:

{
  "corpus_name": "oncology-research",
  "subdomain": "lung-cancer",
  "dedup_mode": "versioned",
  "version_tag": "2026-q1",
  "documents": [
    {
      "source": "paper-001",
      "title": "Breast cancer subtype notes",
      "text": "Triple-negative breast cancer often lacks ER, PR, and HER2 expression.",
      "subdomain": "breast-cancer",
      "cancer_type": "breast cancer",
      "biomarkers": ["ER", "PR", "HER2"],
      "evidence_type": "review",
      "publication_year": 2024,
      "created_at": "2026-03-19T12:00:00Z"
    },
    {
      "source": "paper-002",
      "title": "Targeted therapy planning",
      "text": "Targeted therapies depend on validated biomarkers and specialist review.",
      "cancer_type": "lung cancer",
      "biomarkers": ["EGFR", "ALK", "ROS1"],
      "evidence_type": "guideline",
      "publication_year": 2025
    }
  ]
}

Example oncology query request:

{
  "question": "Summarize common oncology biomarkers for research planning.",
  "subdomain": "lung-cancer",
  "user_id": "researcher-42"
}

Example evidence search request:

{
  "query": "EGFR resistance pathways",
  "subdomain": "lung-cancer",
  "cancer_type": "lung cancer",
  "biomarker": "EGFR",
  "evidence_type": "review",
  "publication_year_from": 2020,
  "publication_year_to": 2026,
  "rerank": true,
  "max_results": 3
}

Evidence response fields now include:

- `citation_id`: stable source-oriented traceability identifier
- `citation_label`: human-readable citation label
- `score`: retrieval score used for ranking
- `rerank_score`: optional lexical+vector blended score when rerank is enabled
- `subdomain`: oncology subdomain such as `lung-cancer` or `breast-cancer`

Ingestion response fields now include:

- `documents_received`: number of incoming documents in the request
- `duplicates_dropped`: dropped items when `dedup_mode=batch-dedup`
- `documents_indexed`: documents persisted after preprocessing
- `dedup_mode`: `upsert`, `batch-dedup`, or `versioned`
- `version_tag`: applied version suffix when `dedup_mode=versioned`

Suggested oncology subdomains:

- `breast-cancer`
- `lung-cancer`
- `colorectal-cancer`
- `hematologic-malignancies`
- `immunotherapy`

Supported corpus import formats:

- JSON: a list of document objects, or an object with a `documents` array
- CSV: columns such as `source`, `title`, `text`, `cancer_type`, `biomarkers`, `evidence_type`, `publication_year`
- TXT: plain text split into sections with `---` delimiters

Example local import commands:

```powershell
.\scripts\import-oncology.ps1
.\scripts\import-oncology.ps1 -Subdomain lung-cancer
.\scripts\import-oncology.ps1 -Path .\data\oncology_sample.json
.venv\Scripts\python.exe manage.py import_oncology_corpus .\data\oncology_sample.json --subdomain lung-cancer
```

Safety note:

- The oncology workflow is intended for research support and knowledge retrieval, not for diagnosis, treatment selection, or clinical decision-making.

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

## Patient Case Analysis (HIPAA-safe)

The API includes a patient-case analysis endpoint for doctors who need case-specific recommendations while enforcing PHI de-identification before model inference.

Endpoint:

- POST /api/v1/agent/patient/analyze/

Payload options:

- `text`: free clinical narrative
- `file`: upload (`.txt`, `.pdf`, `.docx`, `.csv`, `.json`)
- `domain`: cardiology, neurology, oncology, etc.
- `subdomain`: optional specialty focus
- `question`: optional targeted question for the case
- `user_id`: audit/user traceability

Response includes:

- `session_id`: audit session identifier
- `analysis`: evidence-oriented case analysis
- `citations`: references used by the model
- `redaction_summary`: PHI redaction counters by category
- `safety_notice`
- `request_id`

Processing guarantees:

1. Extract text from text/file payload.
2. De-identify PHI (HIPAA Safe Harbor categories) before any LLM call.
3. Build prompt only from de-identified content.
4. Retrieve domain evidence and generate clinical recommendations.
5. Persist audit metadata only (no raw PHI text).

Implementation files:

- `api/agent_ai/phi_deidentifier.py`
- `api/agent_ai/file_extractor.py`
- `api/models.py` (`PatientCaseSession`)
- `api/views.py` (`patient_case_analyze`)
- `api/serializers.py` (`PatientCaseUploadSerializer`, `PatientCaseAnalysisResponseSerializer`)

## Automated Medical Corpus Update

SaaS mode includes scheduled PubMed updates through:

- management command: `manage.py auto_update_corpus`
- container service: `corpus-updater`

Behavior:

1. Query NCBI PubMed for configured specialty topics.
2. Fetch and parse MEDLINE abstracts.
3. Infer evidence type and normalize metadata.
4. Deduplicate against persistent PMID state.
5. Ingest only new evidence to the vector store.

Runtime configuration:

- `CORPUS_UPDATE_INTERVAL_HOURS`
- `NCBI_API_KEY`

Operational scripts:

- `scripts/saas-up.ps1 -Seed`
- `scripts/saas-seed.ps1`
- `scripts/corpus-updater-entrypoint.sh`
