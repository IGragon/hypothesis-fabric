from __future__ import annotations

from unittest.mock import patch

import numpy as np

from hfabric.retriever.vector import merge_results, query_faiss
from hfabric.schemas import EvidenceChunk


class FakeIndex:
    def __init__(self, vectors):
        self.ntotal = len(vectors)
        self._vectors = np.array(vectors, dtype=np.float32)

    def search(self, query, k):
        q = query / (np.linalg.norm(query, axis=1, keepdims=True) + 1e-10)
        scores = np.dot(self._vectors, q.T).flatten()
        k = min(k, len(scores))
        top_indices = np.argsort(scores)[::-1][:k]
        return (
            scores[top_indices].reshape(1, -1),
            top_indices.reshape(1, -1),
        )


def fake_chunks():
    return [
        {
            "chunk_id": "chunk_a",
            "doc_id": "doc_1",
            "text": "Xanthate improves gold flotation recovery.",
            "meta": {"source": "kb", "page": 1},
        },
        {
            "chunk_id": "chunk_b",
            "doc_id": "doc_2",
            "text": "Cyanide depresses pyrite in flotation circuits.",
            "meta": {"source": "kb", "page": 2},
        },
        {
            "chunk_id": "chunk_c",
            "doc_id": "doc_3",
            "text": "Sodium sulphide activates oxidized gold ores.",
            "meta": {"source": "session", "page": 5},
        },
    ]


def fake_load_faiss(index_dir):
    return FakeIndex([[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]]), fake_chunks()


@patch("hfabric.retriever.vector.load_faiss", fake_load_faiss)
def test_query_faiss_returns_chunks():
    results = query_faiss("dummy_dir", [1.0, 0.0], top_k=2)
    assert len(results) == 2
    assert all(isinstance(r, EvidenceChunk) for r in results)
    assert "score" in results[0].meta


@patch("hfabric.retriever.vector.load_faiss", fake_load_faiss)
def test_query_faiss_limits_top_k():
    results = query_faiss("dummy_dir", [1.0, 0.0], top_k=1)
    assert len(results) == 1


def test_merge_results_dedup_prefers_session():
    kb = [
        EvidenceChunk(
            chunk_id="c1",
            doc_id="doc_kb",
            text="KB version",
            meta={"score": 0.5, "source": "kb"},
        )
    ]
    session = [
        EvidenceChunk(
            chunk_id="c1",
            doc_id="doc_sess",
            text="Session version",
            meta={"score": 0.5, "source": "session"},
        )
    ]
    merged = merge_results(kb, session)
    assert len(merged) == 1
    assert merged[0].doc_id == "doc_sess"


def test_merge_results_sorts_by_score_desc():
    kb = [
        EvidenceChunk(
            chunk_id="c1", doc_id="doc_1", text="low",
            meta={"score": 0.3},
        ),
        EvidenceChunk(
            chunk_id="c2", doc_id="doc_2", text="high",
            meta={"score": 0.9},
        ),
    ]
    session: list[EvidenceChunk] = []
    merged = merge_results(kb, session)
    assert merged[0].chunk_id == "c2"
    assert merged[1].chunk_id == "c1"


def test_merge_results_same_score_sorts_by_chunk_id():
    kb = [
        EvidenceChunk(
            chunk_id="c_b", doc_id="doc_b", text="b",
            meta={"score": 0.5},
        ),
        EvidenceChunk(
            chunk_id="c_a", doc_id="doc_a", text="a",
            meta={"score": 0.5},
        ),
    ]
    session: list[EvidenceChunk] = []
    merged = merge_results(kb, session)
    assert merged[0].chunk_id == "c_b"
    assert merged[1].chunk_id == "c_a"
