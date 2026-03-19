import uuid

import requests
from langchain_core.documents import Document

from .config import settings


def _normalize_source(source: str, domain: str | None = None, subdomain: str | None = None) -> str:
    cleaned = (source or "document").strip().strip("/")
    prefixes = []
    if domain:
        prefixes.append(domain.lower())
    if subdomain:
        prefixes.append(subdomain.lower())
    if prefixes:
        prefix = "/".join(prefixes) + "/"
        if not cleaned.lower().startswith(prefix):
            return f"{prefix}{cleaned}"
    return cleaned


def _matches_domain(metadata: dict, domain: str | None = None, subdomain: str | None = None) -> bool:
    if not domain:
        return True
    source = (metadata or {}).get("source", "")
    prefix = domain.lower()
    if subdomain:
        prefix = f"{prefix}/{subdomain.lower()}"
    return source.lower().startswith(f"{prefix}/")


def _document_payload(raw_doc: dict, domain: str | None = None, subdomain: str | None = None) -> dict:
    active_subdomain = (raw_doc.get("subdomain") or subdomain or "").strip()
    return {
        "source": _normalize_source(raw_doc.get("source", "document"), domain=domain, subdomain=active_subdomain or None),
        "title": raw_doc.get("title", ""),
        "text": raw_doc.get("text", ""),
        "subdomain": active_subdomain,
        "cancer_type": raw_doc.get("cancer_type", ""),
        "biomarkers": raw_doc.get("biomarkers", []) or [],
        "evidence_type": raw_doc.get("evidence_type", ""),
        "publication_year": raw_doc.get("publication_year"),
        "created_at": raw_doc.get("created_at"),
    }


def _matches_filters(
    metadata: dict,
    cancer_type: str | None = None,
    biomarker: str | None = None,
    subdomain: str | None = None,
    evidence_type: str | None = None,
    publication_year_from: int | None = None,
    publication_year_to: int | None = None,
) -> bool:
    if subdomain:
        actual_subdomain = str((metadata or {}).get("subdomain") or "")
        if actual_subdomain.strip().lower() != subdomain.strip().lower():
            return False

    if cancer_type:
        actual_cancer_type = str((metadata or {}).get("cancer_type") or "")
        if actual_cancer_type.strip().lower() != cancer_type.strip().lower():
            return False

    if biomarker:
        biomarkers = (metadata or {}).get("biomarkers", []) or []
        if not isinstance(biomarkers, list):
            biomarkers = [str(biomarkers)]
        normalized = {item.strip().lower() for item in biomarkers if isinstance(item, str)}
        if biomarker.strip().lower() not in normalized:
            return False

    if evidence_type:
        actual_evidence_type = str((metadata or {}).get("evidence_type") or "")
        if actual_evidence_type.strip().lower() != evidence_type.strip().lower():
            return False

    if publication_year_from is not None or publication_year_to is not None:
        year_raw = (metadata or {}).get("publication_year")
        try:
            year = int(float(year_raw))
        except (TypeError, ValueError):
            return False

        if publication_year_from is not None and year < publication_year_from:
            return False
        if publication_year_to is not None and year > publication_year_to:
            return False

    return True


class EmptyRetriever:
    def invoke(self, query: str):
        return []

    def add_documents(self, documents, domain: str | None = None, subdomain: str | None = None):
        return 0

    def search_documents(
        self,
        query: str,
        max_results: int = 5,
        cancer_type: str | None = None,
        biomarker: str | None = None,
        subdomain: str | None = None,
        evidence_type: str | None = None,
        publication_year_from: int | None = None,
        publication_year_to: int | None = None,
    ):
        return []

    def close(self):
        return None


class PineconeRetriever:
    def __init__(self, embeddings, domain: str | None = None, subdomain: str | None = None):
        from pinecone import Pinecone

        self.embeddings = embeddings
        self.domain = domain
        self.subdomain = subdomain
        self.pc = Pinecone(api_key=settings.pinecone_api_key)
        self.index = self.pc.Index(settings.pinecone_index)

    def invoke(self, query: str):
        vector = self.embeddings.embed_query(query)
        result = self.index.query(
            vector=vector,
            top_k=settings.max_context_docs,
            namespace=settings.pinecone_namespace,
            include_metadata=True,
        )
        matches = result.get("matches", []) if isinstance(result, dict) else getattr(result, "matches", [])
        docs = []
        for match in matches:
            metadata = match.get("metadata", {}) if isinstance(match, dict) else getattr(match, "metadata", {})
            content = metadata.get("text", "") if isinstance(metadata, dict) else ""
            if content and _matches_domain(metadata, self.domain, self.subdomain):
                score = match.get("score") if isinstance(match, dict) else getattr(match, "score", None)
                if score is not None:
                    metadata = {**metadata, "score": float(score)}
                docs.append(Document(page_content=content, metadata=metadata))
        return docs

    def search_documents(
        self,
        query: str,
        max_results: int = 5,
        cancer_type: str | None = None,
        biomarker: str | None = None,
        subdomain: str | None = None,
        evidence_type: str | None = None,
        publication_year_from: int | None = None,
        publication_year_to: int | None = None,
    ):
        docs = self.invoke(query)
        filtered = []
        for rank, doc in enumerate(docs, start=1):
            metadata = doc.metadata or {}
            if _matches_filters(
                metadata,
                cancer_type=cancer_type,
                biomarker=biomarker,
                subdomain=subdomain or self.subdomain,
                evidence_type=evidence_type,
                publication_year_from=publication_year_from,
                publication_year_to=publication_year_to,
            ):
                if "score" not in metadata:
                    metadata = {**metadata, "score": float(1 / rank)}
                    doc = Document(page_content=doc.page_content, metadata=metadata)
                filtered.append(doc)
            if len(filtered) >= max_results:
                break
        return filtered

    def add_documents(self, documents, domain: str | None = None, subdomain: str | None = None):
        payload = []
        active_domain = domain or self.domain
        active_subdomain = subdomain or self.subdomain
        for raw_doc in documents:
            doc = _document_payload(raw_doc, domain=active_domain, subdomain=active_subdomain)
            if not doc["text"]:
                continue
            payload.append(
                {
                    "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{settings.pinecone_index}:{doc['source']}")),
                    "values": self.embeddings.embed_query(doc["text"]),
                    "metadata": doc,
                }
            )

        if not payload:
            return 0

        self.index.upsert(vectors=payload, namespace=settings.pinecone_namespace)
        return len(payload)

    def close(self):
        return None


class WeaviateRetriever:
    def __init__(self, embeddings, domain: str | None = None, subdomain: str | None = None):
        import weaviate
        from weaviate.auth import AuthApiKey

        self.embeddings = embeddings
        self.domain = domain
        self.subdomain = subdomain
        if settings.weaviate_url:
            auth = AuthApiKey(api_key=settings.weaviate_api_key) if settings.weaviate_api_key else None
            self.client = weaviate.connect_to_weaviate_cloud(
                cluster_url=settings.weaviate_url,
                auth_credentials=auth,
            )
        else:
            self.client = weaviate.connect_to_local(
                host=settings.weaviate_http_host,
                port=settings.weaviate_http_port,
                grpc_port=settings.weaviate_grpc_port,
                skip_init_checks=True,
            )
        self.collection = self.client.collections.get(settings.weaviate_index)

    def invoke(self, query: str):
        vector = self.embeddings.embed_query(query)
        response = self.collection.query.near_vector(
            near_vector=vector,
            limit=settings.max_context_docs,
        )
        docs = []
        for rank, obj in enumerate(getattr(response, "objects", []), start=1):
            properties = getattr(obj, "properties", {}) or {}
            content = properties.get("text", "") if isinstance(properties, dict) else ""
            if content and _matches_domain(properties, self.domain, self.subdomain):
                metadata = dict(properties)
                metadata.setdefault("score", float(1 / rank))
                metadata.setdefault("citation_id", metadata.get("source", f"evidence-{rank}"))
                docs.append(Document(page_content=content, metadata=metadata))
        return docs

    def search_documents(
        self,
        query: str,
        max_results: int = 5,
        cancer_type: str | None = None,
        biomarker: str | None = None,
        subdomain: str | None = None,
        evidence_type: str | None = None,
        publication_year_from: int | None = None,
        publication_year_to: int | None = None,
    ):
        docs = self.invoke(query)
        filtered = []
        for rank, doc in enumerate(docs, start=1):
            metadata = doc.metadata or {}
            if _matches_filters(
                metadata,
                cancer_type=cancer_type,
                biomarker=biomarker,
                subdomain=subdomain or self.subdomain,
                evidence_type=evidence_type,
                publication_year_from=publication_year_from,
                publication_year_to=publication_year_to,
            ):
                if "score" not in metadata or "citation_id" not in metadata:
                    metadata = {
                        **metadata,
                        "score": float(metadata.get("score") or (1 / rank)),
                        "citation_id": metadata.get("source", f"evidence-{rank}"),
                    }
                    doc = Document(page_content=doc.page_content, metadata=metadata)
                filtered.append(doc)
            if len(filtered) >= max_results:
                break
        return filtered

    def add_documents(self, documents, domain: str | None = None, subdomain: str | None = None):
        session = requests.Session()
        base_url = self._base_url()
        self._ensure_schema(session, base_url, settings.weaviate_index)

        inserted = 0
        active_domain = domain or self.domain
        active_subdomain = subdomain or self.subdomain
        for raw_doc in documents:
            doc = _document_payload(raw_doc, domain=active_domain, subdomain=active_subdomain)
            if not doc["text"]:
                continue

            object_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{settings.weaviate_index}:{doc['source']}"))
            payload = {
                "class": settings.weaviate_index,
                "id": object_id,
                "properties": doc,
                "vector": self.embeddings.embed_query(doc["text"]),
            }

            response = session.post(
                f"{base_url}/v1/objects",
                headers=self._headers(),
                json=payload,
                timeout=30,
            )
            if response.status_code in (200, 201):
                inserted += 1
                continue

            if response.status_code in (409, 422) or "already exists" in (response.text or "").lower():
                update_response = session.put(
                    f"{base_url}/v1/objects/{object_id}",
                    headers=self._headers(),
                    json=payload,
                    timeout=30,
                )
                update_response.raise_for_status()
                inserted += 1
                continue

            response.raise_for_status()
            inserted += 1

        return inserted

    @staticmethod
    def _headers():
        if settings.weaviate_url and settings.weaviate_api_key:
            return {"Authorization": f"Bearer {settings.weaviate_api_key}"}
        return {}

    @staticmethod
    def _base_url():
        if settings.weaviate_url:
            return settings.weaviate_url.rstrip("/")
        return f"http://{settings.weaviate_http_host}:{settings.weaviate_http_port}"

    def _ensure_schema(self, session, base_url: str, class_name: str):
        schema = session.get(f"{base_url}/v1/schema", headers=self._headers(), timeout=20)
        schema.raise_for_status()
        body = schema.json()
        classes = [item.get("class") for item in body.get("classes", [])]
        if class_name in classes:
            return

        payload = {
            "class": class_name,
            "description": "Collection for AgentAI local RAG documents",
            "vectorizer": "none",
            "properties": [
                {"name": "text", "dataType": ["text"]},
                {"name": "source", "dataType": ["text"]},
                {"name": "title", "dataType": ["text"]},
                {"name": "subdomain", "dataType": ["text"]},
                {"name": "cancer_type", "dataType": ["text"]},
                {"name": "biomarkers", "dataType": ["text[]"]},
                {"name": "evidence_type", "dataType": ["text"]},
                {"name": "publication_year", "dataType": ["int"]},
                {"name": "created_at", "dataType": ["date"]},
            ],
        }
        response = session.post(f"{base_url}/v1/schema", headers=self._headers(), json=payload, timeout=20)
        response.raise_for_status()

    def close(self):
        try:
            self.client.close()
        except Exception:
            pass


def build_retriever(embeddings, domain: str | None = None, subdomain: str | None = None):
    provider = settings.vector_db_provider.lower()
    try:
        if provider == "pinecone":
            return PineconeRetriever(embeddings, domain=domain, subdomain=subdomain)
        if provider == "weaviate":
            return WeaviateRetriever(embeddings, domain=domain, subdomain=subdomain)
    except Exception:
        return EmptyRetriever()

    raise ValueError(f"Unsupported vector DB provider: {settings.vector_db_provider}")


def build_ingestor(embeddings):
    return build_retriever(embeddings=embeddings, domain=None)
