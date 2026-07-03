from __future__ import annotations


def embed_chunks(
    chunks: list[dict],
    model_name: str = "intfloat/multilingual-e5-small",
) -> list[list[float]]:
    from hfabric.embeddings import SentenceTransformersProvider

    provider = SentenceTransformersProvider(model_name)
    texts = [c["text"] for c in chunks]
    return provider.embed(texts, prefix="passage: ")
