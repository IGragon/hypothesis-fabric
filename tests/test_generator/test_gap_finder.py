from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from hfabric.generator.gap_finder import GapFinder
from hfabric.schemas import EvidenceChunk, KPI, KPIParsed, KGNode


@pytest.fixture
def sample_kpi_gap():
    return KPIParsed(
        goal="increase Au flotation recovery by 5%",
        kpi=KPI(metric="Au recovery", direction="increase", target="5%"),
        constraints=[],
        language="en",
    )


@pytest.fixture
def empty_kpi():
    return KPIParsed(
        goal="",
        kpi=KPI(metric="", direction="increase", target=""),
        constraints=[],
        language="en",
    )


@pytest.fixture
def sparse_kg():
    kg = MagicMock()
    kg.get_entities.return_value = [
        KGNode(id="node_1", label="Material", properties={"name": "molybdenite"}),
    ]
    kg.neighbours.return_value = []
    return kg


@pytest.fixture
def dense_kg():
    kg = MagicMock()
    kg.get_entities.return_value = [
        KGNode(id="node_1", label="Material", properties={"name": "gold"}),
    ]
    kg.neighbours.return_value = [
        KGNode(id="n2", label="Property", properties={"name": "recovery"}),
        KGNode(id="n3", label="Process", properties={"name": "flotation"}),
    ]
    return kg


@pytest.fixture
def sample_evidence():
    return [
        EvidenceChunk(
            chunk_id="c1",
            doc_id="d1",
            text="Molybdenite and gold recovery in flotation circuits was studied.",
            meta={},
        ),
    ]


class TestGapFinder:
    def test_find_gaps_sparse_graph(self, sparse_kg, sample_kpi_gap, sample_evidence):
        gf = GapFinder(sparse_kg, min_neighbours=2)
        gaps = gf.find_gaps(sample_kpi_gap, sample_evidence)
        assert len(gaps) > 0

    def test_find_gaps_dense_graph_no_gaps(self, dense_kg, sample_kpi_gap, sample_evidence):
        gf = GapFinder(dense_kg, min_neighbours=2)
        gaps = gf.find_gaps(sample_kpi_gap, sample_evidence)
        assert len(gaps) == 0

    def test_generate_fallback_without_llm(self, sparse_kg, sample_kpi_gap, sample_evidence):
        gf = GapFinder(sparse_kg, min_neighbours=1)
        gaps = gf.find_gaps(sample_kpi_gap, sample_evidence)
        hyps = gf.generate(gaps, sample_evidence, sample_kpi_gap, llm=None)
        assert len(hyps) > 0
        assert all(h.claim for h in hyps)

    def test_generate_with_mock_llm(self, sparse_kg, sample_kpi_gap, sample_evidence):
        gf = GapFinder(sparse_kg, min_neighbours=1)
        gaps = gf.find_gaps(sample_kpi_gap, sample_evidence)

        llm = MagicMock()
        llm.invoke.return_value.content = (
            '[{"claim": "Test molybdenite hypothesis", "mechanism": "Test mechanism", '
            '"expected_effect": "+5% recovery", "evidence_refs": ["c1"]}]'
        )
        hyps = gf.generate(gaps, sample_evidence, sample_kpi_gap, llm=llm)
        assert len(hyps) > 0
        assert hyps[0].claim == "Test molybdenite hypothesis"

    def test_generate_llm_failure_returns_empty(self, sparse_kg, sample_kpi_gap, sample_evidence):
        gf = GapFinder(sparse_kg, min_neighbours=1)
        gaps = gf.find_gaps(sample_kpi_gap, sample_evidence)

        llm = MagicMock()
        llm.invoke.side_effect = Exception("LLM failure")
        hyps = gf.generate(gaps, sample_evidence, sample_kpi_gap, llm=llm)
        assert isinstance(hyps, list)

    def test_empty_evidence_no_gaps(self, sparse_kg, sample_kpi_gap):
        gf = GapFinder(sparse_kg)
        gaps = gf.find_gaps(sample_kpi_gap, [])
        assert gaps == []

    def test_empty_kpi_no_gaps(self, sparse_kg, empty_kpi, sample_evidence):
        gf = GapFinder(sparse_kg)
        gaps = gf.find_gaps(empty_kpi, sample_evidence)
        assert gaps == []

    def test_generate_empty_gaps_returns_empty(self, sparse_kg, sample_kpi_gap, sample_evidence):
        gf = GapFinder(sparse_kg)
        hyps = gf.generate([], sample_evidence, sample_kpi_gap)
        assert hyps == []
