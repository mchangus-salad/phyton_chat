from dataclasses import dataclass

from .graph import build_agent_graph


@dataclass
class AgentAIResult:
    answer: str
    cache_hit: bool


class AgentAIService:
    def __init__(self):
        self.graph, self.cache = build_agent_graph()

    @staticmethod
    def _cache_key(user_id: str, question: str) -> str:
        return f"agent:{user_id}:{question.strip().lower()}"

    def ask(self, question: str, user_id: str = "anonymous") -> AgentAIResult:
        key = self._cache_key(user_id=user_id, question=question)
        cached = self.cache.get(key)
        if cached:
            return AgentAIResult(answer=cached, cache_hit=True)

        final_state = self.graph.invoke(
            {
                "user_id": user_id,
                "question": question,
                "cache_key": key,
            }
        )
        return AgentAIResult(answer=final_state["answer"], cache_hit=False)
