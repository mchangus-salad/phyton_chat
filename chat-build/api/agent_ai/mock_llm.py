from dataclasses import dataclass


@dataclass
class MockLLMResponse:
    content: str


class MockLLM:
    """Simple local sandbox LLM for development without external APIs."""

    def invoke(self, prompt: str) -> MockLLMResponse:
        question = self._extract(prompt, "Question:")
        context = self._extract(prompt, "Context:")

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

    @staticmethod
    def _extract(prompt: str, marker: str) -> str:
        idx = prompt.find(marker)
        if idx == -1:
            return ""
        return prompt[idx + len(marker):].strip()
