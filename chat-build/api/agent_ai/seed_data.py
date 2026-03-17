from datetime import datetime, timezone


def get_seed_documents():
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "source": "docs/getting-started",
            "text": "AgentAI usa LangGraph para orquestar pasos: recuperar contexto, generar respuesta y persistir eventos.",
            "created_at": now,
        },
        {
            "source": "docs/local-stack",
            "text": "El stack local incluye Redis en 6379, Kafka en 9094 y Weaviate en 8088. Se levanta con docker compose local.",
            "created_at": now,
        },
        {
            "source": "docs/api-endpoint",
            "text": "El endpoint POST /api/agent/query/ recibe question y user_id. Devuelve answer y cache_hit.",
            "created_at": now,
        },
    ]
