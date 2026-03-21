import re
import logging
from typing import TypedDict

from langgraph.graph import StateGraph, END

from .cache import RedisCache
from .embeddings_factory import build_embeddings
from .llm_factory import build_llm
from .prompts import build_context_block, build_history_block, build_system_prompt
from .queue import KafkaEventQueue
from .vector_store import build_retriever
from .mock_llm import MockLLM


logger = logging.getLogger(__name__)


class AgentState(TypedDict, total=False):
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
    llm = build_llm()
    embeddings = build_embeddings()
    retriever = build_retriever(embeddings, domain=domain, subdomain=subdomain)
    cache = RedisCache()
    queue = KafkaEventQueue()

    # ------------------------------------------------------------------
    # Node 1: Retrieve evidence from vector store
    # ------------------------------------------------------------------
    def retrieve_context(state: AgentState) -> AgentState:
        question = state["question"]
        docs = retriever.invoke(question)
        context, citation_labels = build_context_block(docs or [])
        return {**state, "retrieved_docs": docs or [], "context": context, "citation_labels": citation_labels}

    # ------------------------------------------------------------------
    # Node 2: Generate a clinically-structured answer
    # ------------------------------------------------------------------
    def generate_answer(state: AgentState) -> AgentState:
        question = state["question"]
        context = state.get("context", "")
        citation_labels = state.get("citation_labels") or []
        active_domain = state.get("domain") or domain
        active_subdomain = state.get("subdomain") or subdomain
        history = state.get("conversation_history") or []

        system_prompt = build_system_prompt(active_domain)

        # Build the subdomain scoping line
        subdomain_line = ""
        if active_subdomain:
            subdomain_line = f"Focus on the subdomain: {active_subdomain}.\n"

        # Build refence index for the LLM
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
            answer = llm.invoke(prompt).content
        except Exception:
            # Keep clinical workflows responsive in local/dev when the configured LLM backend is unstable.
            logger.exception("primary llm invoke failed; using mock fallback")
            answer = MockLLM().invoke(prompt).content
        return {**state, "answer": answer}

    # ------------------------------------------------------------------
    # Node 3: Extract cited references from the generated answer
    # ------------------------------------------------------------------
    def extract_citations(state: AgentState) -> AgentState:
        answer = state.get("answer", "")
        citation_labels = state.get("citation_labels") or []

        cited: list[str] = []
        seen: set[int] = set()

        for match in re.finditer(r"\[(\d+)\]", answer):
            idx = int(match.group(1)) - 1  # convert to 0-based
            if 0 <= idx < len(citation_labels) and idx not in seen:
                cited.append(citation_labels[idx])
                seen.add(idx)

        return {**state, "citations": cited}

    # ------------------------------------------------------------------
    # Node 4: Persist answer to cache and publish to event queue
    # ------------------------------------------------------------------
    def persist_and_emit(state: AgentState) -> AgentState:
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
