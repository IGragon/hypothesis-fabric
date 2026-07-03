from __future__ import annotations

from unittest.mock import MagicMock

from hfabric.retriever.rerank import rerank_evidence
from hfabric.schemas import EvidenceChunk


def _chunk(cid, text):
    return EvidenceChunk(
        chunk_id=cid, doc_id=f"doc_{cid}", text=text, meta={}
    )


def _make_llm(json_str):
    llm = MagicMock()
    response = MagicMock()
    response.content = json_str
    llm.invoke.return_value = response
    return llm


def test_rerank_returns_reranked_order():
    evidence = [
        _chunk("c1", "Cyanide depresses pyrite in flotation circuits."),
        _chunk("c2", "Xanthate collectors improve gold flotation recovery by up to 10%."),
        _chunk("c3", "Water quality affects flotation kinetics significantly."),
    ]
    llm = _make_llm('["c2", "c3", "c1"]')

    reranked, low_conf = rerank_evidence(evidence, "increase gold recovery", llm, top_k=8)
    assert reranked[0].chunk_id == "c2"
    assert reranked[1].chunk_id == "c3"
    assert reranked[2].chunk_id == "c1"


def test_rerank_returns_top_k():
    evidence = [
        _chunk("c1", "chunk 1 long enough text " * 20),
        _chunk("c2", "chunk 2 long enough text " * 20),
        _chunk("c3", "chunk 3 long enough text " * 20),
    ]
    llm = _make_llm('["c3", "c1", "c2"]')

    reranked, low_conf = rerank_evidence(evidence, "some goal", llm, top_k=2)
    assert len(reranked) == 2
    assert reranked[0].chunk_id == "c3"


def test_rerank_llm_failure_fallback():
    evidence = [
        _chunk("c1", "chunk 1 long enough text " * 20),
        _chunk("c2", "chunk 2 long enough text " * 20),
    ]
    llm = MagicMock()
    llm.invoke.side_effect = RuntimeError("LLM down")

    reranked, low_conf = rerank_evidence(evidence, "goal", llm, top_k=8)
    assert len(reranked) == 2
    assert reranked[0].chunk_id == "c1"


def test_rerank_invalid_json_fallback():
    evidence = [
        _chunk("c1", "chunk 1 long enough text " * 20),
        _chunk("c2", "chunk 2 long enough text " * 20),
    ]
    llm = _make_llm("not valid json at all !!!")

    reranked, low_conf = rerank_evidence(evidence, "goal", llm, top_k=8)
    assert len(reranked) == 2
    assert reranked[0].chunk_id == "c1"


def test_rerank_empty_evidence():
    reranked, low_conf = rerank_evidence([], "goal", MagicMock(), top_k=8)
    assert reranked == []
    assert low_conf is True


def test_rerank_low_confidence_on_short_text():
    evidence = [
        _chunk("c1", "Short."),
    ]
    llm = _make_llm('["c1"]')

    reranked, low_conf = rerank_evidence(evidence, "goal", llm, top_k=8)
    assert low_conf is True
