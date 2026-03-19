# AgentAI Mermaid Diagrams

This file visualizes the current system behavior and structure.

## How to Read These Diagrams

Recommended order:

1. Start with Runtime Architecture to understand the system components.
2. Continue with Agent Query Execution Flow to see request-time behavior.
3. Review Oncology Ingestion and Evidence Flow to understand domain-specific pipelines.
4. Finish with Data Model and Movement to map payload fields and output structure.

Interpretation tips:

- Boxes represent components or processing stages.
- Arrows represent request or data movement direction.
- Decision diamonds represent conditional logic (for example, dedup mode or rerank enabled).
- Sequence diagram participants are ordered by responsibility from API entrypoint to downstream services.
- ER entities describe the shape of stored/retrieved document metadata, not SQL tables.

## 1) Runtime Architecture

```mermaid
flowchart LR
    Client[Client or Frontend]
    API[Django + DRF API]
    Auth[JWT / API Key Permission]
    Views[api/views.py]
    Service[AgentAIService]
    Graph[LangGraph Pipeline]
    LLM[LLM Provider\nGPT / Claude / Mock]
    Embed[Embeddings Provider\nOpenAI / HuggingFace / Local]
    Vector[Vector DB\nWeaviate / Pinecone]
    Cache[Redis Cache]
    Events[Kafka Events]

    Client --> API
    API --> Auth
    Auth --> Views
    Views --> Service
    Service --> Graph
    Graph --> LLM
    Graph --> Vector
    Service --> Embed
    Graph --> Cache
    Graph --> Events
```

## 2) Agent Query Execution Flow

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant V as DRF View
    participant S as AgentAIService
    participant C as Redis Cache
    participant G as LangGraph
    participant R as Retriever
    participant L as LLM

    U->>V: POST /api/v1/agent/query
    V->>S: ask(question, user_id)
    S->>C: GET cache_key
    alt Cache hit
        C-->>S: cached answer
        S-->>V: answer + cache_hit=true
    else Cache miss
        S->>G: invoke(state)
        G->>R: retrieve context docs
        R-->>G: ranked docs
        G->>L: generate answer with context
        L-->>G: answer
        G->>C: SET cache_key
        G-->>S: final state
        S-->>V: answer + cache_hit=false
    end
    V-->>U: JSON response + request_id
```

## 3) Oncology Ingestion and Evidence Flow

```mermaid
flowchart TD
    A[Source Data\nJSON / CSV / TXT / Upload] --> B[Oncology Parser]
    B --> C[Document Normalization\nsource + metadata]
    C --> D{dedup_mode}
    D -->|upsert| E[Deterministic IDs]
    D -->|batch-dedup| F[Drop payload duplicates]
    D -->|versioned| G[Append @version_tag to source]
    E --> H[Vector Ingestion]
    F --> H
    G --> H
    H --> I[Vector DB Collection]

    J[POST /oncology/evidence] --> K[Metadata Filters]
    K --> L[Similarity Retrieval]
    L --> M{rerank enabled?}
    M -->|yes| N[Lexical + Vector rerank]
    M -->|no| O[Original ranking]
    N --> P[Structured Evidence Output]
    O --> P
```

## 4) Data Model and Movement

```mermaid
erDiagram
    KNOWLEDGE_DOCUMENT {
        string source
        string title
        string text
        string subdomain
        string cancer_type
        string[] biomarkers
        string evidence_type
        int publication_year
        datetime created_at
    }

    EVIDENCE_RESULT {
        string citation_id
        string citation_label
        float score
        float rerank_score
        string source
        string title
        string text
        string subdomain
        string cancer_type
        string[] biomarkers
        string evidence_type
        int publication_year
    }

    KNOWLEDGE_DOCUMENT ||--o{ EVIDENCE_RESULT : retrieved_as
```
