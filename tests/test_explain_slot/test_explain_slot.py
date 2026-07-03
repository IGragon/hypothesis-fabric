from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from hfabric.explain.explain_slot import (
    ExplainSlot,
    _build_kg_neighbourhood,
    _parse_llm_response,
)
from hfabric.schemas import (
    EvidenceChunk,
    ExplainedHypothesis,
    Hypothesis,
    ScoredHypothesis,
    TraceRecord,
)


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    response = MagicMock()
    response.content = (
        "JUSTIFICATION: Xanthate collectors are known to chemisorb on gold surfaces, "
        "increasing hydrophobicity and improving flotation recovery.\n"
        "UNCERTAINTY: The exact recovery improvement depends on ore composition and "
        "collector dosage.\n"
        "VERIFICATION: Run lab-scale flotation tests with varying xanthate "
        "concentrations and measure Au recovery.\n"
    )
    llm.invoke.return_value = response
    return llm


@pytest.fixture
def sample_scored() -> ScoredHypothesis:
    return ScoredHypothesis(
        hypothesis=Hypothesis(
            claim="Xanthate collector addition increases Au recovery",
            mechanism="Xanthates chemisorb on gold surfaces increasing hydrophobicity",
            expected_effect="+5-10% Au recovery",
            evidence_refs=["chunk_001"],
        ),
        score=0.85,
        features={"novelty": 0.5, "feasibility": 0.8, "effect": 0.9},
        cited_refs={
            "chunk_001": EvidenceChunk(
                chunk_id="chunk_001",
                doc_id="doc_1",
                text="Xanthate collectors improve gold flotation recovery by up to 10%.",
                meta={"source": "kb"},
            ),
        },
    )


class TestParseResponse:
    def test_parse_full_response(self):
        response = (
            "JUSTIFICATION: This is plausible.\n"
            "UNCERTAINTY: Some gaps remain.\n"
            "VERIFICATION: Test in lab.\n"
        )
        j, u, v = _parse_llm_response(response)
        assert j == "This is plausible."
        assert u == "Some gaps remain."
        assert v == "Test in lab."

    def test_parse_partial_response(self):
        response = "JUSTIFICATION: Only justification provided."
        j, u, v = _parse_llm_response(response)
        assert j == "Only justification provided."
        assert u == "Unknown."
        assert v == "Experimental validation recommended."

    def test_parse_empty_response(self):
        j, u, v = _parse_llm_response("")
        assert j == "Based on the evidence provided."
        assert u == "Unknown."
        assert v == "Experimental validation recommended."

    def test_parse_unordered_sections(self):
        response = (
            "VERIFICATION: Test it.\n"
            "JUSTIFICATION: Makes sense.\n"
            "UNCERTAINTY: Not sure.\n"
        )
        j, u, v = _parse_llm_response(response)
        assert j == "Makes sense."
        assert u == "Not sure."
        assert v == "Test it."

    def test_parse_empty_section_content_uses_fallback(self):
        response = (
            "JUSTIFICATION:\n"
            "UNCERTAINTY: Real uncertainty.\n"
            "VERIFICATION:\n"
        )
        j, u, v = _parse_llm_response(response)
        assert j == "Based on the evidence provided."
        assert u == "Real uncertainty."
        assert v == "Experimental validation recommended."


class TestBuildKGNeighbourhood:
    def test_returns_lines(self, sample_scored, fake_kg):
        lines = _build_kg_neighbourhood(sample_scored, fake_kg)
        assert isinstance(lines, list)
        assert len(lines) > 0

    def test_includes_entity_labels(self, sample_scored, fake_kg):
        lines = _build_kg_neighbourhood(sample_scored, fake_kg)
        combined = " ".join(lines)
        assert "Material" in combined

    def test_includes_influences_relation(self, sample_scored, fake_kg):
        lines = _build_kg_neighbourhood(sample_scored, fake_kg)
        combined = " ".join(lines)
        assert "influences" in combined

    def test_kg_exception_handled(self, sample_scored):
        kg = MagicMock()
        kg.get_entities.side_effect = RuntimeError("KG down")
        lines = _build_kg_neighbourhood(sample_scored, kg)
        assert lines == []


class TestExplainSlot:
    def test_explain_single_hypothesis(self, mock_llm, sample_scored, fake_kg):
        slot = ExplainSlot(mock_llm)
        evidence = [
            EvidenceChunk(
                chunk_id="chunk_001",
                doc_id="doc_1",
                text="Xanthate collectors improve gold flotation recovery.",
                meta={},
            ),
        ]

        result = slot.explain([sample_scored], evidence, fake_kg)

        assert len(result) == 1
        assert isinstance(result[0], ExplainedHypothesis)
        assert result[0].scored == sample_scored
        assert "Xanthate" in result[0].justification
        assert result[0].uncertainty != ""
        assert result[0].verification_plan != ""

    def test_explain_multiple_hypotheses(self, mock_llm, fake_kg):
        slot = ExplainSlot(mock_llm)
        scored_list = [
            ScoredHypothesis(
                hypothesis=Hypothesis(
                    claim="Claim A",
                    mechanism="Mech A",
                    expected_effect="Effect A",
                    evidence_refs=["chunk_001"],
                ),
                score=0.9,
                features={"novelty": 0.5, "feasibility": 0.8, "effect": 0.9},
                cited_refs={
                    "chunk_001": EvidenceChunk(
                        chunk_id="chunk_001",
                        doc_id="doc_1",
                        text="Evidence for A.",
                        meta={},
                    ),
                },
            ),
            ScoredHypothesis(
                hypothesis=Hypothesis(
                    claim="Claim B",
                    mechanism="Mech B",
                    expected_effect="Effect B",
                    evidence_refs=["chunk_002"],
                ),
                score=0.7,
                features={"novelty": 0.3, "feasibility": 0.7, "effect": 0.6},
                cited_refs={
                    "chunk_002": EvidenceChunk(
                        chunk_id="chunk_002",
                        doc_id="doc_2",
                        text="Evidence for B.",
                        meta={},
                    ),
                },
            ),
        ]
        evidence = [
            EvidenceChunk(chunk_id="chunk_001", doc_id="doc_1", text="Evidence A.", meta={}),
            EvidenceChunk(chunk_id="chunk_002", doc_id="doc_2", text="Evidence B.", meta={}),
        ]

        result = slot.explain(scored_list, evidence, fake_kg)

        assert len(result) == 2
        assert result[0].scored == scored_list[0]
        assert result[1].scored == scored_list[1]

    def test_kg_neighbourhood_populated(self, mock_llm, sample_scored, fake_kg):
        slot = ExplainSlot(mock_llm)
        evidence = [
            EvidenceChunk(
                chunk_id="chunk_001",
                doc_id="doc_1",
                text="Xanthate collectors improve gold flotation recovery.",
                meta={},
            ),
        ]

        result = slot.explain([sample_scored], evidence, fake_kg)

        assert len(result[0].graph_neighbourhood) > 0
        any_label = any(
            "Material" in line or "Property" in line or "influences" in line
            for line in result[0].graph_neighbourhood
        )
        assert any_label

    def test_llm_failure_fallback(self, sample_scored, fake_kg):
        llm = MagicMock()
        llm.invoke.side_effect = RuntimeError("LLM unavailable")

        slot = ExplainSlot(llm)
        evidence = [
            EvidenceChunk(
                chunk_id="chunk_001",
                doc_id="doc_1",
                text="Some evidence.",
                meta={},
            ),
        ]

        result = slot.explain([sample_scored], evidence, fake_kg)

        assert len(result) == 1
        assert result[0].justification == "Based on the evidence provided."
        assert result[0].uncertainty == "Unknown."
        assert result[0].verification_plan == "Experimental validation recommended."

    def test_empty_ranked_list(self, mock_llm, fake_kg):
        slot = ExplainSlot(mock_llm)
        result = slot.explain([], [], fake_kg)
        assert result == []

    def test_evidence_map_as_dict(self, mock_llm, sample_scored, fake_kg):
        slot = ExplainSlot(mock_llm)
        evidence_dict = {
            "chunk_001": EvidenceChunk(
                chunk_id="chunk_001",
                doc_id="doc_1",
                text="Xanthate collectors improve gold flotation.",
                meta={},
            ),
        }

        result = slot.explain([sample_scored], evidence_dict, fake_kg)

        assert len(result) == 1
        assert result[0].justification != ""

    def test_trace_recording(self, mock_llm, sample_scored, fake_kg):
        slot = ExplainSlot(mock_llm)
        trace = TraceRecord(run_id="test_run", stage="explain")
        evidence = [
            EvidenceChunk(
                chunk_id="chunk_001",
                doc_id="doc_1",
                text="Xanthate collectors improve gold flotation.",
                meta={},
            ),
        ]

        result = slot.explain([sample_scored], evidence, fake_kg, trace=trace)

        assert len(result) == 1
        assert trace.token_in > 0
        assert trace.token_out > 0
        assert trace.latency_ms >= 0

    def test_trace_records_on_failure(self, sample_scored, fake_kg):
        llm = MagicMock()
        llm.invoke.side_effect = RuntimeError("LLM down")

        slot = ExplainSlot(llm)
        trace = TraceRecord(run_id="test_run", stage="explain")
        evidence = [
            EvidenceChunk(
                chunk_id="chunk_001",
                doc_id="doc_1",
                text="Some evidence.",
                meta={},
            ),
        ]

        result = slot.explain([sample_scored], evidence, fake_kg, trace=trace)

        assert len(result) == 1
        assert trace.token_in > 0
        assert trace.token_out == 0
        assert trace.latency_ms >= 0
