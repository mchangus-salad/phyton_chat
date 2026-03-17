import uuid

import requests
from requests import HTTPError
from django.core.management.base import BaseCommand

from api.agent_ai.config import settings
from api.agent_ai.embeddings_factory import build_embeddings
from api.agent_ai.seed_data import get_seed_documents


class Command(BaseCommand):
    help = "Seed local Weaviate with starter documents (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--base-url", default=None, help="Override Weaviate base URL, e.g. http://127.0.0.1:8088")

    def handle(self, *args, **options):
        if settings.vector_db_provider.lower() != "weaviate":
            self.stdout.write(self.style.WARNING("Skipping seed: AGENT_VECTOR_DB_PROVIDER is not weaviate."))
            return

        base_url = options.get("base_url") or self._build_base_url()
        class_name = settings.weaviate_index
        session = requests.Session()

        self.stdout.write(f"Using Weaviate at {base_url}")
        self._ensure_schema(session, base_url, class_name)

        embeddings = build_embeddings()
        docs = get_seed_documents()

        try:
            inserted = self._upsert_documents(session, base_url, class_name, docs, embeddings)
        except HTTPError as exc:
            response_text = exc.response.text if exc.response is not None else str(exc)
            status_code = exc.response.status_code if exc.response is not None else None

            # Local dev recovery path: schema drift or vector incompatibility can surface as Weaviate 500.
            should_recover = (status_code is not None and status_code >= 500) or self._is_vector_mismatch_error(response_text)
            if should_recover:
                self.stdout.write(self.style.WARNING("Error de Weaviate detectado durante seed. Recreando coleccion y reintentando una vez."))
                self.stdout.write(self.style.WARNING(f"Detalle original: {response_text}"))
                self._recreate_schema(session, base_url, class_name)
                inserted = self._upsert_documents(session, base_url, class_name, docs, embeddings)
            else:
                raise

        self.stdout.write(self.style.SUCCESS(f"Seed completed. Upserted {inserted} documents into {class_name}."))

    def _upsert_documents(self, session: requests.Session, base_url: str, class_name: str, docs, embeddings):
        inserted = 0
        for doc in docs:
            text = doc["text"]
            source = doc["source"]
            obj_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{class_name}:{source}"))
            vector = embeddings.embed_query(text)
            payload = {
                "class": class_name,
                "id": obj_id,
                "properties": {
                    "text": text,
                    "source": source,
                    "created_at": doc.get("created_at"),
                },
                "vector": vector,
            }

            create_response = session.post(
                f"{base_url}/v1/objects",
                json=payload,
                timeout=30,
            )

            if create_response.status_code in (200, 201):
                inserted += 1
                continue

            create_text = (create_response.text or "").lower()
            if create_response.status_code in (409, 422) or "already exists" in create_text:
                update_response = session.put(
                    f"{base_url}/v1/objects/{obj_id}",
                    json=payload,
                    timeout=30,
                )
                update_response.raise_for_status()
                inserted += 1
                continue

            create_response.raise_for_status()
            inserted += 1
        return inserted

    @staticmethod
    def _is_vector_mismatch_error(error_text: str) -> bool:
        text = (error_text or "").lower()
        return "vector" in text and ("dimension" in text or "length" in text)

    def _build_base_url(self):
        if settings.weaviate_url:
            return settings.weaviate_url.rstrip("/")
        return f"http://{settings.weaviate_http_host}:{settings.weaviate_http_port}"

    def _ensure_schema(self, session: requests.Session, base_url: str, class_name: str):
        schema = session.get(f"{base_url}/v1/schema", timeout=20)
        schema.raise_for_status()
        body = schema.json()
        classes = [c.get("class") for c in body.get("classes", [])]

        if class_name in classes:
            return

        payload = {
            "class": class_name,
            "description": "Collection for AgentAI local RAG documents",
            "vectorizer": "none",
            "properties": [
                {"name": "text", "dataType": ["text"]},
                {"name": "source", "dataType": ["text"]},
                {"name": "created_at", "dataType": ["date"]},
            ],
        }
        response = session.post(f"{base_url}/v1/schema", json=payload, timeout=20)
        response.raise_for_status()

    def _recreate_schema(self, session: requests.Session, base_url: str, class_name: str):
        session.delete(f"{base_url}/v1/schema/{class_name}", timeout=20)
        self._ensure_schema(session, base_url, class_name)
