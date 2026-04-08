"""High-level service interface for the CliniGraph AI agent.

This module exposes ``AgentAIService``, which wraps the LangGraph pipeline and
provides three query modes: synchronous (``ask``), conversational
(``ask_with_history``), and streaming (``ask_stream``).

All heavy provider construction (LLM, embeddings, retriever, graph) happens
once during ``__init__`` and is reused across calls for efficiency.
"""
from dataclasses import dataclass
import re

from .embeddings_factory import build_embeddings
from .graph import build_agent_graph
from .llm_factory import build_llm
from .mock_llm import MockLLM
from .prompts import build_context_block, build_history_block, build_system_prompt
from .queue import KafkaEventQueue
from .vector_store import build_ingestor, build_retriever


@dataclass
class AgentAIResult:
    answer: str
    cache_hit: bool
    citations: list[str] | None = None


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
    """Facade over the LangGraph RAG pipeline for clinical decision support.

    Instantiate once per request (or cache it) and call ``ask``, ``ask_with_history``,
    or ``ask_stream`` depending on the query mode required.

    Example::

        svc = AgentAIService(domain="oncology", subdomain="lung-cancer")
        result = svc.ask("What are EGFR mutation prevalence rates?")
        print(result.answer, result.citations)
    """

    def __init__(self, domain: str | None = None, subdomain: str | None = None, initialize_graph: bool = True):
        """Initialise the service and all downstream providers.

        Args:
            domain: Clinical domain used to scope the vector store retrieval and
                select the speciality system prompt (e.g. ``"oncology"``).
            subdomain: Sub-speciality narrowing (e.g. ``"lung-cancer"``).
            initialize_graph: When ``False`` only the ingestor is built, skipping
                the LLM / graph initialisation.  Used by train/upload endpoints.
        """
        self.domain = domain
        self.subdomain = subdomain
        embeddings = build_embeddings()
        self.ingestor = build_ingestor(embeddings)
        self.graph = None
        self.cache = None
        self.retriever = None
        self.queue = KafkaEventQueue()

        if initialize_graph:
            self.graph, self.cache = build_agent_graph(domain=domain, subdomain=subdomain)
            self.retriever = build_retriever(embeddings, domain=domain, subdomain=subdomain)

    def _cache_key(self, user_id: str, question: str) -> str:
        domain_part = self.domain or "general"
        subdomain_part = self.subdomain or "default"
        return f"agent:{domain_part}:{subdomain_part}:{user_id}:{question.strip().lower()}"

    def ask(self, question: str, user_id: str = "anonymous") -> AgentAIResult:
        """Answer a single question using the RAG pipeline.

        Returns a cached ``AgentAIResult`` when an identical question was recently
        answered for the same user/domain/subdomain (cache TTL is configured via
        ``AGENT_CACHE_TTL_SECONDS``).  On cache miss the full LangGraph pipeline
        runs: retrieve → generate → cite → persist.

        Args:
            question: The clinical question string (plain text).
            user_id: Caller identifier used as part of the cache key.

        Returns:
            ``AgentAIResult`` with ``answer``, ``cache_hit`` flag, and ``citations``.

        Raises:
            RuntimeError: If the service was created with ``initialize_graph=False``.
        """
        if self.graph is None or self.cache is None:
            raise RuntimeError("AgentAIService was initialized without query capabilities")

        key = self._cache_key(user_id=user_id, question=question)
        cached = self.cache.get(key)
        if cached:
            return AgentAIResult(answer=cached, cache_hit=True, citations=None)

        final_state = self.graph.invoke(
            {
                "user_id": user_id,
                "question": question,
                "cache_key": key,
                "domain": self.domain,
                "subdomain": self.subdomain,
                "conversation_history": [],
            }
        )
        return AgentAIResult(
            answer=final_state["answer"],
            cache_hit=False,
            citations=final_state.get("citations") or [],
        )

    def ask_with_history(
        self,
        question: str,
        conversation_history: list[dict],
        user_id: str = "anonymous",
    ) -> AgentAIResult:
        """Multi-turn query that passes prior conversation context to the LLM.

        conversation_history: list of {"role": "user"|"assistant", "content": str}
        The cache is intentionally bypassed for multi-turn queries to avoid stale
        context collisions across different conversation threads.
        """
        if self.graph is None:
            raise RuntimeError("AgentAIService was initialized without query capabilities")

        final_state = self.graph.invoke(
            {
                "user_id": user_id,
                "question": question,
                "cache_key": f"no-cache:{user_id}:{question[:40]}",
                "domain": self.domain,
                "subdomain": self.subdomain,
                "conversation_history": conversation_history or [],
            }
        )
        return AgentAIResult(
            answer=final_state["answer"],
            cache_hit=False,
            citations=final_state.get("citations") or [],
        )

    def ask_stream(
        self,
        question: str,
        user_id: str = "anonymous",
        conversation_history: list[dict] | None = None,
    ):
        """Yield streaming events for progressive answer rendering.

        Event payloads:
        - {"event": "delta", "delta": "..."}
        - {"event": "done", "answer": "...", "cache_hit": bool, "citations": list[str]}
        """
        if self.cache is None or self.retriever is None:
            raise RuntimeError("AgentAIService was initialized without query capabilities")

        history = conversation_history or []
        cache_hit = False
        key = self._cache_key(user_id=user_id, question=question)

        if not history:
            cached = self.cache.get(key)
            if cached:
                cache_hit = True
                yield {"event": "delta", "delta": cached}
                yield {"event": "done", "answer": cached, "cache_hit": True, "citations": []}
                return

        docs = self.retriever.invoke(question)
        context, citation_labels = build_context_block(docs or [])
        system_prompt = build_system_prompt(self.domain)
        history_block = build_history_block(history)

        subdomain_line = ""
        if self.subdomain:
            subdomain_line = f"Focus on the subdomain: {self.subdomain}.\n"

        ref_index = ""
        if citation_labels:
            entries = "\n".join(f"  [{i+1}] {lbl}" for i, lbl in enumerate(citation_labels))
            ref_index = f"\nREFERENCE INDEX:\n{entries}\n"

        context_section = f"\nREVIEWED EVIDENCE:\n{context}" if context else (
            "\nREVIEWED EVIDENCE: (none retrieved - answer from model knowledge only, note this limitation)"
        )

        prompt = (
            f"{system_prompt}\n\n"
            f"{subdomain_line}"
            f"{ref_index}"
            f"{history_block}"
            f"{context_section}\n\n"
            f"QUESTION:\n{question}"
        )

        llm = build_llm()
        buffer: list[str] = []

        try:
            if hasattr(llm, "stream"):
                for chunk in llm.stream(prompt):
                    text = self._extract_stream_text(chunk)
                    if not text:
                        continue
                    buffer.append(text)
                    yield {"event": "delta", "delta": text}
            else:
                answer = (llm.invoke(prompt).content or "")
                if answer:
                    buffer.append(answer)
                    yield {"event": "delta", "delta": answer}
        except Exception:
            # Keep local/dev flows responsive when provider streaming fails.
            answer = (MockLLM().invoke(prompt).content or "")
            if answer:
                buffer.append(answer)
                yield {"event": "delta", "delta": answer}

        answer = "".join(buffer).strip()
        citations = self._extract_citations_from_answer(answer=answer, citation_labels=citation_labels)

        if not history and answer:
            self.cache.set(key, answer)

        self.queue.publish(
            {
                "type": "agent_answer_created",
                "user_id": user_id,
                "question": question,
                "answer": answer,
                "domain": self.domain or "general",
                "subdomain": self.subdomain,
                "citations": citations,
            }
        )

        yield {
            "event": "done",
            "answer": answer,
            "cache_hit": cache_hit,
            "citations": citations,
        }

    @staticmethod
    def _extract_stream_text(chunk) -> str:
        """Normalize stream chunk objects from different LangChain providers."""
        if chunk is None:
            return ""
        if isinstance(chunk, str):
            return chunk

        content = getattr(chunk, "content", None)
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
            return "".join(parts)

        text_attr = getattr(chunk, "text", None)
        if isinstance(text_attr, str):
            return text_attr
        return ""

    @staticmethod
    def _extract_citations_from_answer(answer: str, citation_labels: list[str]) -> list[str]:
        cited: list[str] = []
        seen: set[int] = set()

        for match in re.finditer(r"\[(\d+)\]", answer or ""):
            idx = int(match.group(1)) - 1
            if 0 <= idx < len(citation_labels) and idx not in seen:
                cited.append(citation_labels[idx])
                seen.add(idx)

        return cited

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
        """Weighted reranker combining lexical overlap, evidence quality, and recency."""
        # Evidence-type quality weights (higher = stronger evidence)
        _EVIDENCE_WEIGHTS: dict[str, float] = {
            "meta-analysis": 1.0,
            "systematic-review": 0.95,
            "systematic review": 0.95,
            "clinical-trial": 0.85,
            "rct": 0.85,
            "randomized": 0.85,
            "randomised": 0.85,
            "cohort": 0.65,
            "prospective": 0.65,
            "retrospective": 0.55,
            "case-control": 0.50,
            "case control": 0.50,
            "case-series": 0.35,
            "case series": 0.35,
            "case-report": 0.20,
            "case report": 0.20,
            "guideline": 0.80,
            "consensus": 0.75,
            "review": 0.45,
            "expert-opinion": 0.25,
            "opinion": 0.25,
            "editorial": 0.20,
        }
        _CURRENT_YEAR = 2026
        query_tokens = set(re.findall(r"[a-zA-Z0-9\-]+", (query or "").lower()))

        ranked = []
        for doc in docs:
            metadata = dict(doc.metadata or {})
            text = doc.page_content or ""

            # Lexical overlap score (normalised by query length to avoid length bias)
            text_tokens = set(re.findall(r"[a-zA-Z0-9\-]+", text.lower()))
            overlap = len(query_tokens & text_tokens) / max(len(query_tokens), 1)

            # Vector similarity (already computed by Weaviate/Pinecone)
            vector_score = float(metadata.get("score") or 0.0)

            # Evidence quality bonus
            etype = (metadata.get("evidence_type") or "").lower()
            quality_bonus = max(
                (_EVIDENCE_WEIGHTS[k] for k in _EVIDENCE_WEIGHTS if k in etype),
                default=0.3,
            )

            # Recency bonus: +0.05 for each decade newer than 2000, capped at 0.25
            pub_year = int(metadata.get("publication_year") or 0)
            recency_bonus = min(max((pub_year - 2000) / 10 * 0.05, 0.0), 0.25) if pub_year > 0 else 0.0

            rerank_score = (overlap * 0.25) + (vector_score * 0.40) + (quality_bonus * 0.25) + (recency_bonus * 0.10)
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
