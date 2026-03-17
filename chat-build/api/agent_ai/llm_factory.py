from .config import settings
from .mock_llm import MockLLM


def build_llm():
    provider = settings.llm_provider.lower()

    if provider in ("mock", "sandbox"):
        return MockLLM()

    if provider == "gpt":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=settings.llm_model, api_key=settings.openai_api_key, temperature=0)

    if provider == "claude":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=settings.llm_model, api_key=settings.anthropic_api_key, temperature=0)

    raise ValueError(f"Unsupported LLM provider: {settings.llm_provider}")
