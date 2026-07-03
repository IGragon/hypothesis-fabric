from __future__ import annotations

import numpy as np

from hfabric.etl.faiss_index import load_faiss
from hfabric.schemas import EvidenceChunk


def query_faiss(
    index_dir: str, query_vector: list[float], top_k: int = 20
) -> list[EvidenceChunk]:
    index, chunks = load_faiss(index_dir)
    qv = np.array(query_vector, dtype=np.float32).reshape(1, -1)

    qv_norm = np.linalg.norm(qv)
    if qv_norm > 0:
        qv = qv / qv_norm

    k = min(top_k, index.ntotal)
    if k == 0:
        return []

    scores, indices = index.search(qv, k)

    results: list[EvidenceChunk] = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0 or idx >= len(chunks):
            continue
        chunk_data = chunks[idx]
        results.append(
            EvidenceChunk(
                chunk_id=chunk_data["chunk_id"],
                doc_id=chunk_data.get("doc_id", ""),
                text=chunk_data["text"],
                meta={**chunk_data.get("meta", {}), "score": float(score)},
            )
        )

    return results


def merge_results(
    kb_results: list[EvidenceChunk],
    session_results: list[EvidenceChunk],
) -> list[EvidenceChunk]:
    merged: dict[str, EvidenceChunk] = {}

    for chunk in kb_results:
        merged[chunk.chunk_id] = chunk

    for chunk in session_results:
        merged[chunk.chunk_id] = chunk

    result_list = list(merged.values())
    result_list.sort(
        key=lambda c: (c.meta.get("score", 0.0), c.chunk_id),
        reverse=True,
    )

    return result_list
