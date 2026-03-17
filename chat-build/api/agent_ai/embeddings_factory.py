from .config import settings
from .local_embeddings import LocalDeterministicEmbeddings


def build_embeddings():
    provider = settings.embeddings_provider.lower()

    if provider == "openai":
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(model=settings.embeddings_model, api_key=settings.openai_api_key)

    if provider == "huggingface":
        from langchain_huggingface import HuggingFaceEmbeddings

        return HuggingFaceEmbeddings(model_name=settings.embeddings_model)

    if provider == "local":
        # Offline deterministic embeddings for local dev and smoke tests.
        return LocalDeterministicEmbeddings(dimension=256)

    raise ValueError(f"Unsupported embeddings provider: {settings.embeddings_provider}")
