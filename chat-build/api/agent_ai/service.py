from dataclasses import dataclass
import re

from .embeddings_factory import build_embeddings
from .graph import build_agent_graph
from .vector_store import build_ingestor, build_retriever


@dataclass
class AgentAIResult:
    answer: str
    cache_hit: bool


@dataclass
class KnowledgeIngestionResult:
    domain: str
    subdomain: str | None
    documents_received: int
    duplicates_dropped: int
    documents_indexed: int
    dedup_mode: str
    version_tag: str


@dataclass
class EvidenceSearchResult:
    domain: str
    subdomain: str | None
    evidence: list[dict]


class AgentAIService:
    def __init__(self, domain: str | None = None, subdomain: str | None = None, initialize_graph: bool = True):
        self.domain = domain
        self.subdomain = subdomain
        embeddings = build_embeddings()
        self.ingestor = build_ingestor(embeddings)
        self.graph = None
        self.cache = None
        self.retriever = None

        if initialize_graph:
            self.graph, self.cache = build_agent_graph(domain=domain, subdomain=subdomain)
            self.retriever = build_retriever(embeddings, domain=domain, subdomain=subdomain)

    def _cache_key(self, user_id: str, question: str) -> str:
        domain_part = self.domain or "general"
        subdomain_part = self.subdomain or "default"
        return f"agent:{domain_part}:{subdomain_part}:{user_id}:{question.strip().lower()}"

    def ask(self, question: str, user_id: str = "anonymous") -> AgentAIResult:
        if self.graph is None or self.cache is None:
            raise RuntimeError("AgentAIService was initialized without query capabilities")

        key = self._cache_key(user_id=user_id, question=question)
        cached = self.cache.get(key)
        if cached:
            return AgentAIResult(answer=cached, cache_hit=True)

        final_state = self.graph.invoke(
            {
                "user_id": user_id,
                "question": question,
                "cache_key": key,
                "domain": self.domain,
                "subdomain": self.subdomain,
            }
        )
        return AgentAIResult(answer=final_state["answer"], cache_hit=False)

    def ingest_documents(
        self,
        documents: list[dict],
        domain: str | None = None,
        subdomain: str | None = None,
        dedup_mode: str = "upsert",
        version_tag: str | None = None,
    ) -> KnowledgeIngestionResult:
        """Ingest documents with optional batch deduplication or versioned source expansion.

        dedup_mode values:
        - upsert: source-based deterministic ids update existing vectors
        - batch-dedup: remove duplicates inside current payload before upsert
        - versioned: append @version to source key to keep multiple versions side by side
        """
        active_domain = domain or self.domain or "general"
        active_subdomain = subdomain if subdomain is not None else self.subdomain

        prepared_docs, duplicates_dropped, active_version = self._prepare_documents_for_ingestion(
            documents=documents,
            dedup_mode=dedup_mode,
            version_tag=version_tag,
        )
        indexed = self.ingestor.add_documents(documents=prepared_docs, domain=active_domain, subdomain=active_subdomain)
        return KnowledgeIngestionResult(
            domain=active_domain,
            subdomain=active_subdomain,
            documents_received=len(documents),
            duplicates_dropped=duplicates_dropped,
            documents_indexed=indexed,
            dedup_mode=dedup_mode,
            version_tag=active_version,
        )

    def search_evidence(
        self,
        query: str,
        max_results: int = 5,
        condition: str | None = None,
        marker: str | None = None,
        cancer_type: str | None = None,
        biomarker: str | None = None,
        subdomain: str | None = None,
        evidence_type: str | None = None,
        publication_year_from: int | None = None,
        publication_year_to: int | None = None,
        rerank: bool = True,
    ) -> EvidenceSearchResult:
        if self.retriever is None:
            raise RuntimeError("AgentAIService was initialized without retrieval capabilities")

        docs = self.retriever.search_documents(
            query=query,
            max_results=max_results,
            condition=condition,
            marker=marker,
            cancer_type=cancer_type,
            biomarker=biomarker,
            subdomain=subdomain if subdomain is not None else self.subdomain,
            evidence_type=evidence_type,
            publication_year_from=publication_year_from,
            publication_year_to=publication_year_to,
        )

        if rerank:
            docs = self._rerank_documents(query=query, docs=docs)

        evidence = []
        for rank, doc in enumerate(docs, start=1):
            metadata = dict(doc.metadata or {})
            metadata["text"] = doc.page_content
            metadata.setdefault("score", float(1 / rank))
            metadata.setdefault("rerank_score", float(metadata.get("score") or (1 / rank)))
            metadata.setdefault("citation_id", metadata.get("source", f"evidence-{rank}"))
            metadata.setdefault(
                "citation_label",
                self._build_citation_label(metadata),
            )
            evidence.append(metadata)
        return EvidenceSearchResult(domain=self.domain or "general", subdomain=subdomain if subdomain is not None else self.subdomain, evidence=evidence)

    @staticmethod
    def _build_citation_label(metadata: dict) -> str:
        title = (metadata.get("title") or metadata.get("source") or "Untitled evidence").strip()
        year = metadata.get("publication_year")
        evidence_type = (metadata.get("evidence_type") or "evidence").strip()
        suffix = f" ({year}, {evidence_type})" if year else f" ({evidence_type})"
        return f"{title}{suffix}"

    @staticmethod
    def _prepare_documents_for_ingestion(
        documents: list[dict],
        dedup_mode: str,
        version_tag: str | None,
    ) -> tuple[list[dict], int, str]:
        """Prepare corpus payload before storage with deterministic dedup/version rules."""
        prepared = [dict(item) for item in documents]
        duplicates_dropped = 0
        active_version = (version_tag or "").strip()

        if dedup_mode == "batch-dedup":
            seen = set()
            unique_docs = []
            for item in prepared:
                dedup_key = (item.get("source", ""), item.get("title", ""), item.get("text", ""))
                if dedup_key in seen:
                    duplicates_dropped += 1
                    continue
                seen.add(dedup_key)
                unique_docs.append(item)
            prepared = unique_docs

        if dedup_mode == "versioned":
            active_version = active_version or "v1"
            for item in prepared:
                source = (item.get("source") or "document").strip()
                item["source"] = f"{source}@{active_version}"

        return prepared, duplicates_dropped, active_version

    @staticmethod
    def _rerank_documents(query: str, docs: list):
        """Apply a lightweight lexical reranker on top of vector similarity results."""
        query_tokens = set(re.findall(r"[a-zA-Z0-9\-]+", (query or "").lower()))
        ranked = []
        for doc in docs:
            metadata = dict(doc.metadata or {})
            text = doc.page_content or ""
            text_tokens = set(re.findall(r"[a-zA-Z0-9\-]+", text.lower()))
            overlap = len(query_tokens & text_tokens)
            vector_score = float(metadata.get("score") or 0.0)
            rerank_score = (overlap * 0.2) + vector_score
            metadata["rerank_score"] = rerank_score
            ranked.append((rerank_score, doc.__class__(page_content=doc.page_content, metadata=metadata)))

        ranked.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in ranked]

    def close(self):
        close_ingestor = getattr(self.ingestor, 'close', None)
        if callable(close_ingestor):
            close_ingestor()

        close_retriever = getattr(self.retriever, 'close', None)
        if callable(close_retriever) and self.retriever is not self.ingestor:
            close_retriever()


# Progressive internal rebrand aliases (non-breaking):
# Existing AgentAI* symbols remain the canonical implementation for compatibility.
CliniGraphResult = AgentAIResult
CliniGraphIngestionResult = KnowledgeIngestionResult
CliniGraphEvidenceResult = EvidenceSearchResult


class CliniGraphService(AgentAIService):
    """Alias class for the CliniGraph AI brand while preserving AgentAI compatibility."""


__all__ = [
    "AgentAIResult",
    "KnowledgeIngestionResult",
    "EvidenceSearchResult",
    "AgentAIService",
    "CliniGraphResult",
    "CliniGraphIngestionResult",
    "CliniGraphEvidenceResult",
    "CliniGraphService",
]
