import hashlib
from typing import List

from langchain_core.embeddings import Embeddings


class LocalDeterministicEmbeddings(Embeddings):
    def __init__(self, dimension: int = 256):
        self.dimension = dimension

    def _embed_text(self, text: str) -> List[float]:
        values = [0.0] * self.dimension
        text = (text or "").strip().lower()
        if not text:
            return values

        tokens = text.split()
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "little") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            values[idx] += sign

        norm = sum(v * v for v in values) ** 0.5
        if norm > 0:
            values = [v / norm for v in values]
        return values

    def embed_query(self, text: str) -> List[float]:
        return self._embed_text(text)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._embed_text(t) for t in texts]
