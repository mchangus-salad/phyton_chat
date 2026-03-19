from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(PROJECT_ROOT / ".env.agentai.local")
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class AgentAISettings:
    llm_provider: str = os.getenv("AGENT_LLM_PROVIDER", "gpt")
    llm_model: str = os.getenv("AGENT_LLM_MODEL", "gpt-4o-mini")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

    embeddings_provider: str = os.getenv("AGENT_EMBEDDINGS_PROVIDER", "openai")
    embeddings_model: str = os.getenv("AGENT_EMBEDDINGS_MODEL", "text-embedding-3-small")

    vector_db_provider: str = os.getenv("AGENT_VECTOR_DB_PROVIDER", "pinecone")
    pinecone_api_key: str = os.getenv("PINECONE_API_KEY", "")
    pinecone_index: str = os.getenv("PINECONE_INDEX", "agent-ai-index")
    pinecone_namespace: str = os.getenv("PINECONE_NAMESPACE", "default")

    weaviate_url: str = os.getenv("WEAVIATE_URL", "")
    weaviate_api_key: str = os.getenv("WEAVIATE_API_KEY", "")
    weaviate_index: str = os.getenv("WEAVIATE_INDEX", "AgentDocuments")
    weaviate_http_host: str = os.getenv("WEAVIATE_HTTP_HOST", "127.0.0.1")
    weaviate_http_port: int = int(os.getenv("WEAVIATE_HTTP_PORT", "8088"))
    weaviate_grpc_host: str = os.getenv("WEAVIATE_GRPC_HOST", "127.0.0.1")
    weaviate_grpc_port: int = int(os.getenv("WEAVIATE_GRPC_PORT", "50051"))
    weaviate_secure: bool = os.getenv("WEAVIATE_SECURE", "false").lower() == "true"

    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    cache_ttl_seconds: int = int(os.getenv("AGENT_CACHE_TTL_SECONDS", "300"))

    kafka_bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    kafka_topic: str = os.getenv("AGENT_KAFKA_TOPIC", "agent-events")

    max_context_docs: int = int(os.getenv("AGENT_MAX_CONTEXT_DOCS", "4"))


settings = AgentAISettings()

# Progressive internal rebrand aliases (non-breaking).
CliniGraphSettings = AgentAISettings
clinigraph_settings = settings
