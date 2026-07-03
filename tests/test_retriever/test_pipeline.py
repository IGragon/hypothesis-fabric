from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from hfabric.config import MVPConfig
from hfabric.retriever import Retriever
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


def _fake_chunks():
    filler = " extra text for tokens " * 30
    return [
        {
            "chunk_id": "c1",
            "doc_id": "doc_1",
            "text": "Xanthate collectors improve gold flotation recovery by up to 10%." + filler,
            "meta": {"source": "kb", "page": 1},
        },
        {
            "chunk_id": "c2",
            "doc_id": "doc_1",
            "text": "Cyanide is commonly used as a depressant in flotation circuits." + filler,
            "meta": {"source": "kb", "page": 2},
        },
        {
            "chunk_id": "c3",
            "doc_id": "doc_2",
            "text": "Sodium sulphide can activate oxidized gold ores in flotation." + filler,
            "meta": {"source": "session", "page": 5},
        },
    ]


def _fake_load_faiss(index_dir):
    return FakeIndex([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]), _fake_chunks()


class FakeEmbeddings:
    def embed(self, texts, prefix=""):
        return [[0.5, 0.3, 0.2] for _ in texts]

    @property
    def dim(self):
        return 3


class FakeLLMResponse:
    content = '["c1", "c3", "c2"]'


def test_full_pipeline(sample_kpi, fake_kg):
    config = MVPConfig()

    llm = MagicMock()
    llm.invoke.return_value = FakeLLMResponse()

    with patch("hfabric.retriever.vector.load_faiss", _fake_load_faiss), \
         patch("hfabric.llm.create_chat_model", return_value=llm):
        retriever = Retriever(
            embeddings=FakeEmbeddings(),
            kg=fake_kg,
            config=config,
        )
        result = retriever.retrieve(sample_kpi, config, session_id="test_session")

    assert "evidence" in result
    assert "low_confidence" in result
    assert len(result["evidence"]) > 0
    for chunk in result["evidence"]:
        assert isinstance(chunk, EvidenceChunk)


def test_pipeline_merges_kb_and_session(sample_kpi):
    config = MVPConfig()

    kg = MagicMock()
    kg.get_entities.return_value = []
    kg.neighbours.return_value = []

    llm = MagicMock()
    llm.invoke.return_value = FakeLLMResponse()

    with patch("hfabric.retriever.vector.load_faiss", _fake_load_faiss), \
         patch("hfabric.llm.create_chat_model", return_value=llm):
        retriever = Retriever(
            embeddings=FakeEmbeddings(),
            kg=kg,
            config=config,
        )
        result = retriever.retrieve(sample_kpi, config, session_id="test_session")

    assert len(result["evidence"]) > 0
