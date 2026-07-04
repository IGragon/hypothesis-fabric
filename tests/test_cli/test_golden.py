from __future__ import annotations

import json
from pathlib import Path

import pytest

from hfabric.explain.citation_bind import bind_claims
from hfabric.schemas import EvidenceChunk, Hypothesis

GOLDEN_DIR = Path(__file__).parent.parent / "golden"


def _load_golden_citations():
    path = GOLDEN_DIR / "golden_citations.json"
    if not path.exists():
        return []
    return json.loads(path.read_text())


def _load_golden_rankings():
    path = GOLDEN_DIR / "golden_rankings.json"
    if not path.exists():
        return []
    return json.loads(path.read_text())


RU_CHUNK_001 = EvidenceChunk(
    chunk_id="chunk_ru_001",
    doc_id="doc_ru_1",
    text="Применение ксантогенатных собирателей увеличивает извлечение золота на 5-10% при флотации.",
    meta={"source": "kb", "page": 1},
)

SAMPLE_CHUNKS = {
    "chunk_001": EvidenceChunk(
        chunk_id="chunk_001",
        doc_id="doc_1",
        text="Xanthate collectors improve gold flotation recovery by up to 10%.",
        meta={"source": "kb", "page": 1},
    ),
    "chunk_003": EvidenceChunk(
        chunk_id="chunk_003",
        doc_id="doc_2",
        text="Sodium sulphide can activate oxidized gold ores in flotation.",
        meta={"source": "session", "page": 5},
    ),
    "chunk_ru_001": RU_CHUNK_001,
}


class TestGoldenCitations:
    @pytest.mark.parametrize("golden", _load_golden_citations())
    def test_golden_citation(self, golden):
        hyp = Hypothesis(
            claim=golden["claim"],
            mechanism="test mechanism",
            expected_effect="positive effect",
            evidence_refs=golden["expected_chunk_ids"],
        )
        scored, coverage = bind_claims([hyp], SAMPLE_CHUNKS, threshold=55.0)
        for expected_id in golden["expected_chunk_ids"]:
            assert expected_id in scored[0].cited_refs, (
                f"Expected chunk {expected_id} to be cited for claim: {golden['claim']}"
            )


class TestGoldenRankings:
    @pytest.mark.parametrize("golden", _load_golden_rankings())
    def test_golden_ranking_format(self, golden):
        assert "query" in golden
        assert "expected_ranked_claims" in golden
        assert len(golden["expected_ranked_claims"]) > 0
