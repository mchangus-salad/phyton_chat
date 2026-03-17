from langchain_core.documents import Document

from .config import settings


class EmptyRetriever:
    def invoke(self, query: str):
        return []


class PineconeRetriever:
    def __init__(self, embeddings):
        from pinecone import Pinecone

        self.embeddings = embeddings
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
            if content:
                docs.append(Document(page_content=content, metadata=metadata))
        return docs


class WeaviateRetriever:
    def __init__(self, embeddings):
        import weaviate
        from weaviate.auth import AuthApiKey

        self.embeddings = embeddings
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
        for obj in getattr(response, "objects", []):
            properties = getattr(obj, "properties", {}) or {}
            content = properties.get("text", "") if isinstance(properties, dict) else ""
            if content:
                docs.append(Document(page_content=content, metadata=properties))
        return docs


def build_retriever(embeddings):
    provider = settings.vector_db_provider.lower()
    try:
        if provider == "pinecone":
            return PineconeRetriever(embeddings)
        if provider == "weaviate":
            return WeaviateRetriever(embeddings)
    except Exception:
        return EmptyRetriever()

    raise ValueError(f"Unsupported vector DB provider: {settings.vector_db_provider}")
