"""LangGraph-based RAG pipeline for CliniGraph AI.

The compiled graph executes four sequential nodes for every query::

    retrieve_context → generate_answer → extract_citations → persist_and_emit

Use ``build_agent_graph(domain, subdomain)`` to obtain a compiled graph and its
associated ``RedisCache`` instance.  The graph is stateless — each invocation
receives and returns a fresh ``AgentState`` dict.
"""
import re
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _TimeoutError
from typing import TypedDict

from opentelemetry import trace as otel_trace
from langgraph.graph import StateGraph, END

from .cache import RedisCache
from .embeddings_factory import build_embeddings
from .llm_factory import build_llm
from .prompts import build_context_block, build_history_block, build_system_prompt
from .queue import KafkaEventQueue
from .vector_store import build_retriever
from .mock_llm import MockLLM
from .config import settings


logger = logging.getLogger(__name__)
_tracer = otel_trace.get_tracer(__name__)


class AgentState(TypedDict, total=False):
    """Mutable state dict passed between graph nodes during a single query execution.

    Nodes add or update keys; the final state after ``persist_and_emit`` contains
    the complete answer with citations ready to return to the caller.
    """

    user_id: str
    question: str
    # raw docs are stored only during graph execution, cleared before caching
    retrieved_docs: list
    context: str
    citation_labels: list[str]
    answer: str
    citations: list[str]
    cache_key: str
    domain: str
    subdomain: str
    # list of {"role": "user"|"assistant", "content": str}
    conversation_history: list[dict]


def build_agent_graph(domain: str | None = None, subdomain: str | None = None):
    """Build and compile the CliniGraph AI LangGraph pipeline.

    Constructs all provider instances (LLM, embeddings, vector store, cache, queue)
    and wires the four-node sequential graph::

        retrieve_context → generate_answer → extract_citations → persist_and_emit

    Args:
        domain: Optional clinical domain scope (e.g. ``"oncology"``).  Affects
            the vector store namespace and the system prompt selected.
        subdomain: Optional sub-speciality (e.g. ``"lung-cancer"``). Used to
            prefix the focus instruction injected into the LLM prompt.

    Returns:
        A 2-tuple ``(compiled_graph, cache)`` where ``compiled_graph`` is the
        LangGraph ``CompiledStateGraph`` ready for ``.invoke()`` calls and
        ``cache`` is the shared ``RedisCache`` instance.
    """
    llm = build_llm()
    embeddings = build_embeddings()
    retriever = build_retriever(embeddings, domain=domain, subdomain=subdomain)
    cache = RedisCache()
    queue = KafkaEventQueue()

    # ------------------------------------------------------------------
    # Node 1: Retrieve evidence from vector store
    # ------------------------------------------------------------------
    def retrieve_context(state: AgentState) -> AgentState:
        """Fetch the top-k relevant documents from the vector store."""
        with _tracer.start_as_current_span("rag.retrieve_context") as span:
            question = state["question"]
            span.set_attribute("rag.domain", domain or "")
            span.set_attribute("rag.subdomain", subdomain or "")
            docs = retriever.invoke(question)
            context, citation_labels = build_context_block(docs or [])
            span.set_attribute("rag.docs_retrieved", len(docs or []))
            return {**state, "retrieved_docs": docs or [], "context": context, "citation_labels": citation_labels}

    # ------------------------------------------------------------------
    # Node 2: Generate a clinically-structured answer
    # ------------------------------------------------------------------
    def generate_answer(state: AgentState) -> AgentState:
        """Invoke the configured LLM with context and conversation history.

        A per-call timeout (``settings.llm_timeout_seconds``) prevents worker
        threads from hanging indefinitely on slow or unresponsive LLM backends.
        On timeout or any other error the ``MockLLM`` fallback is used so
        clinical workflows stay responsive in degraded environments.
        """
        with _tracer.start_as_current_span("rag.generate_answer") as span:
            question = state["question"]
            context = state.get("context", "")
            citation_labels = state.get("citation_labels") or []
            active_domain = state.get("domain") or domain
            active_subdomain = state.get("subdomain") or subdomain
            history = state.get("conversation_history") or []

            span.set_attribute("rag.llm_provider", settings.llm_provider)
            span.set_attribute("rag.domain", active_domain or "")
            span.set_attribute("rag.history_turns", len(history))

            system_prompt = build_system_prompt(active_domain)

            # Build the subdomain scoping line
            subdomain_line = ""
            if active_subdomain:
                subdomain_line = f"Focus on the subdomain: {active_subdomain}.\n"

            # Build reference index for the LLM
            ref_index = ""
            if citation_labels:
                entries = "\n".join(f"  [{i+1}] {lbl}" for i, lbl in enumerate(citation_labels))
                ref_index = f"\nREFERENCE INDEX:\n{entries}\n"

            history_block = build_history_block(history)

            context_section = f"\nREVIEWED EVIDENCE:\n{context}" if context else (
                "\nREVIEWED EVIDENCE: (none retrieved — answer from model knowledge only, note this limitation)"
            )

            prompt = (
                f"{system_prompt}\n\n"
                f"{subdomain_line}"
                f"{ref_index}"
                f"{history_block}"
                f"{context_section}\n\n"
                f"QUESTION:\n{question}"
            )

            try:
                with ThreadPoolExecutor(max_workers=1) as _pool:
                    _future = _pool.submit(llm.invoke, prompt)
                    answer = _future.result(timeout=settings.llm_timeout_seconds).content
            except _TimeoutError:
                logger.warning(
                    "LLM invoke timed out after %s s; using mock fallback",
                    settings.llm_timeout_seconds,
                )
                answer = MockLLM().invoke(prompt).content
            except Exception:
                # Keep clinical workflows responsive in local/dev when the configured LLM backend is unstable.
                logger.exception("primary llm invoke failed; using mock fallback")
                answer = MockLLM().invoke(prompt).content

            span.set_attribute("rag.answer_length", len(answer))
            return {**state, "answer": answer}

    # ------------------------------------------------------------------
    # Node 3: Extract cited references from the generated answer
    # ------------------------------------------------------------------
    def extract_citations(state: AgentState) -> AgentState:
        """Parse ``[n]`` reference markers in the answer and resolve them to labels."""
        with _tracer.start_as_current_span("rag.extract_citations") as span:
            answer = state.get("answer", "")
            citation_labels = state.get("citation_labels") or []

            cited: list[str] = []
            seen: set[int] = set()

            for match in re.finditer(r"\[(\d+)\]", answer):
                idx = int(match.group(1)) - 1  # convert to 0-based
                if 0 <= idx < len(citation_labels) and idx not in seen:
                    cited.append(citation_labels[idx])
                    seen.add(idx)

            span.set_attribute("rag.citations_found", len(cited))
            return {**state, "citations": cited}

    # ------------------------------------------------------------------
    # Node 4: Persist answer to cache and publish to event queue
    # ------------------------------------------------------------------
    def persist_and_emit(state: AgentState) -> AgentState:
        """Write the final answer to Redis cache and publish a Kafka event."""
        with _tracer.start_as_current_span("rag.persist_and_emit"):
            cache_key = state["cache_key"]
            answer = state["answer"]
            # Cache only the answer text (not docs) to keep memory lean
            cache.set(cache_key, answer)
            queue.publish(
                {
                    "type": "agent_answer_created",
                    "user_id": state.get("user_id", "anonymous"),
                    "question": state["question"],
                    "answer": answer,
                    "domain": state.get("domain") or domain,
                    "subdomain": state.get("subdomain") or subdomain,
                    "citations": state.get("citations") or [],
                }
            )
            return state

    graph = StateGraph(AgentState)
    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("generate_answer", generate_answer)
    graph.add_node("extract_citations", extract_citations)
    graph.add_node("persist_and_emit", persist_and_emit)

    graph.set_entry_point("retrieve_context")
    graph.add_edge("retrieve_context", "generate_answer")
    graph.add_edge("generate_answer", "extract_citations")
    graph.add_edge("extract_citations", "persist_and_emit")
    graph.add_edge("persist_and_emit", END)

    return graph.compile(), cache
