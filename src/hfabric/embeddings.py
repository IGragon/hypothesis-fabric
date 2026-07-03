from __future__ import annotations

from typing import Protocol


class EmbeddingsProvider(Protocol):
    def embed(self, texts: list[str], prefix: str = "") -> list[list[float]]:
        ...

    @property
    def dim(self) -> int:
        ...


class SentenceTransformersProvider:
    def __init__(self, model_name: str = "intfloat/multilingual-e5-small"):
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)

    def embed(self, texts: list[str], prefix: str = "") -> list[list[float]]:
        prefixed = [f"{prefix}{t}" for t in texts]
        embeddings = self._model.encode(prefixed, normalize_embeddings=True)
        return embeddings.tolist()

    @property
    def dim(self) -> int:
        return self._model.get_embedding_dimension()
