from typing import TypedDict

from langgraph.graph import StateGraph, END

from .cache import RedisCache
from .embeddings_factory import build_embeddings
from .llm_factory import build_llm
from .queue import KafkaEventQueue
from .vector_store import build_retriever


class AgentState(TypedDict, total=False):
    user_id: str
    question: str
    context: str
    answer: str
    cache_key: str


def build_agent_graph():
    llm = build_llm()
    embeddings = build_embeddings()
    retriever = build_retriever(embeddings)
    cache = RedisCache()
    queue = KafkaEventQueue()

    def retrieve_context(state: AgentState) -> AgentState:
        question = state["question"]
        docs = retriever.invoke(question)
        context = "\n\n".join([d.page_content for d in docs]) if docs else ""
        return {**state, "context": context}

    def generate_answer(state: AgentState) -> AgentState:
        question = state["question"]
        context = state.get("context", "")
        prompt = (
            "You are an assistant for a Web API. Use the retrieved context when useful. "
            "If context is empty, answer from model knowledge and mention assumptions.\n\n"
            f"Context:\n{context}\n\nQuestion:\n{question}"
        )
        answer = llm.invoke(prompt).content
        return {**state, "answer": answer}

    def persist_and_emit(state: AgentState) -> AgentState:
        cache_key = state["cache_key"]
        answer = state["answer"]
        cache.set(cache_key, answer)
        queue.publish(
            {
                "type": "agent_answer_created",
                "user_id": state.get("user_id", "anonymous"),
                "question": state["question"],
                "answer": answer,
            }
        )
        return state

    graph = StateGraph(AgentState)
    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("generate_answer", generate_answer)
    graph.add_node("persist_and_emit", persist_and_emit)

    graph.set_entry_point("retrieve_context")
    graph.add_edge("retrieve_context", "generate_answer")
    graph.add_edge("generate_answer", "persist_and_emit")
    graph.add_edge("persist_and_emit", END)

    return graph.compile(), cache
