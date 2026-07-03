from __future__ import annotations

from hfabric.retriever.budget import count_tokens, truncate_to_budget
from hfabric.schemas import EvidenceChunk


def test_count_tokens_non_empty():
    tokens = count_tokens("Hello world")
    assert tokens > 0
    assert tokens < 10


def test_count_tokens_empty():
    assert count_tokens("") == 0


def test_truncate_to_budget_under_limit():
    chunks = [
        EvidenceChunk(chunk_id="c1", doc_id="d1", text="short text", meta={}),
        EvidenceChunk(chunk_id="c2", doc_id="d2", text="another short text", meta={}),
    ]
    result = truncate_to_budget(chunks, budget_tokens=10000)
    assert len(result) == 2


def test_truncate_to_budget_removes_from_end():
    long_text = "word " * 1000
    chunks = [
        EvidenceChunk(chunk_id="c1", doc_id="d1", text=long_text, meta={}),
        EvidenceChunk(chunk_id="c2", doc_id="d2", text=long_text, meta={}),
        EvidenceChunk(chunk_id="c3", doc_id="d3", text=long_text, meta={}),
    ]
    budget = count_tokens(long_text) * 2 + 1
    result = truncate_to_budget(chunks, budget_tokens=budget)
    assert len(result) == 2
    assert result[-1].chunk_id == "c2"


def test_truncate_to_budget_empty():
    assert truncate_to_budget([], budget_tokens=100) == []


def test_truncate_to_budget_preserves_order():
    chunks = [
        EvidenceChunk(chunk_id="a", doc_id="d1", text="first", meta={}),
        EvidenceChunk(chunk_id="b", doc_id="d2", text="second", meta={}),
        EvidenceChunk(chunk_id="c", doc_id="d3", text="third", meta={}),
    ]
    result = truncate_to_budget(chunks, budget_tokens=10000)
    assert [c.chunk_id for c in result] == ["a", "b", "c"]
