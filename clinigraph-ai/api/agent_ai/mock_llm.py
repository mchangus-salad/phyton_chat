import time
from dataclasses import dataclass


@dataclass
class MockLLMResponse:
    content: str


class MockLLM:
    """Simple local sandbox LLM for development without external APIs."""

    def invoke(self, prompt: str) -> MockLLMResponse:
        question = self._extract(prompt, "QUESTION:\n") or self._extract(prompt, "Question:")
        context = self._extract(prompt, "REVIEWED EVIDENCE:\n") or self._extract(prompt, "Context:")

        # Strip the "none retrieved" placeholder so it counts as empty context
        if context and "none retrieved" in context:
            context = ""

        if context:
            summary = context.split("\n")[0][:300]
            answer = (
                "[sandbox] Respuesta generada por MockLLM local. "
                f"Pregunta: {question}\n"
                f"Contexto relevante: {summary}\n"
                "Siguiente paso sugerido: valida este flujo con un proveedor real (GPT/Claude) cuando tengas API key."
            )
        else:
            answer = (
                "[sandbox] No encontre contexto en la base vectorial local. "
                f"Pregunta: {question}\n"
                "Puedes ejecutar scripts/dev-seed.ps1 para cargar documentos semilla."
            )

        return MockLLMResponse(content=answer)

    def stream(self, prompt: str):
        """Yield response word-by-word to simulate LLM token streaming in local/dev mode.

        This ensures the streaming pipeline is exercised end-to-end without requiring
        a real API key. Yields ~25 tokens/sec — comparable to a fast real LLM.
        """
        response = self.invoke(prompt)
        words = response.content.split(" ")
        for i, word in enumerate(words):
            token = word if i == 0 else f" {word}"
            yield MockLLMResponse(content=token)
            time.sleep(0.04)

    @staticmethod
    def _extract(prompt: str, marker: str) -> str:
        idx = prompt.find(marker)
        if idx == -1:
            return ""
        return prompt[idx + len(marker):].strip()
