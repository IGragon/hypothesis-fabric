from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from hfabric.explain.explain_slot import (
    ExplainSlot,
    _ExplainOutput,
    _build_kg_neighbourhood,
    _cited_in,
    _gate_sections,
)
from hfabric.schemas import (
    EvidenceChunk,
    ExplainedHypothesis,
    Hypothesis,
    ScoredHypothesis,
    TraceRecord,
)


def _full_output(cite: str = "chunk_001") -> _ExplainOutput:
    return _ExplainOutput(
        justification=f"Xanthate collectors chemisorb on gold [{cite}].",
        uncertainty=f"Depends on ore composition [{cite}].",
        verification_plan=f"Run lab-scale flotation tests [{cite}].",
        effect_cause_examples=[f"If dosage rises then recovery rises [{cite}]."],
        general_approach=f"Collectors increase hydrophobicity [{cite}].",
        actionable_now=f"Bench test three dosages this week [{cite}].",
        why_it_matters=f"Directly lifts Au recovery KPI [{cite}].",
        best_practices=f"Standard xanthate dosing [{cite}].",
        novelty=f"Incremental over baseline [{cite}].",
        risks=f"Reagent cost increase [{cite}].",
    )


def _structured_llm(output: _ExplainOutput) -> MagicMock:
    llm = MagicMock()
    structured = MagicMock()
    structured.invoke.return_value = output
    llm.with_structured_output.return_value = structured
    return llm


@pytest.fixture
def mock_llm():
    return _structured_llm(_full_output())


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


class TestCitationGate:
    def test_cited_in_matches_known_ids(self):
        assert _cited_in("foo [c1] bar [c2]", {"c1"}) == ["c1"]

    def test_gate_flags_uncovered_sections(self):
        available = {
            "c1": EvidenceChunk(chunk_id="c1", doc_id="d", text="t", meta={}),
        }
        data = {
            "justification": "grounded [c1]",
            "uncertainty": "no citation here",
            "verification_plan": "",
            "general_approach": "x [c1]",
            "actionable_now": "y [c1]",
            "why_it_matters": "z [c1]",
            "best_practices": "w [c1]",
            "novelty": "n [c1]",
            "risks": "r [c1]",
        }
        section_citations, uncovered = _gate_sections(data, available)
        assert section_citations["justification"] == ["c1"]
        assert uncovered == 2
        assert "нет подтверждающих доказательств" in data["uncertainty"]


class TestBuildKGNeighbourhood:
    def test_returns_lines(self, sample_scored, fake_kg):
        lines = _build_kg_neighbourhood(sample_scored, fake_kg)
        assert isinstance(lines, list)
        assert len(lines) > 0

    def test_includes_entity_labels(self, sample_scored, fake_kg):
        lines = _build_kg_neighbourhood(sample_scored, fake_kg)
        assert "Material" in " ".join(lines)

    def test_includes_influences_relation(self, sample_scored, fake_kg):
        lines = _build_kg_neighbourhood(sample_scored, fake_kg)
        assert "influences" in " ".join(lines)

    def test_kg_exception_handled(self, sample_scored):
        kg = MagicMock()
        kg.get_entities.side_effect = RuntimeError("KG down")
        lines = _build_kg_neighbourhood(sample_scored, kg)
        assert lines == []


class TestExplainSlot:
    def test_explain_single_hypothesis(self, mock_llm, sample_scored, fake_kg):
        slot = ExplainSlot(mock_llm)
        evidence = [
            EvidenceChunk(chunk_id="chunk_001", doc_id="doc_1",
                          text="Xanthate collectors improve gold flotation recovery.", meta={}),
        ]
        result = slot.explain([sample_scored], evidence, fake_kg)

        assert len(result) == 1
        assert isinstance(result[0], ExplainedHypothesis)
        assert result[0].scored == sample_scored
        assert "Xanthate" in result[0].justification
        assert result[0].uncertainty != ""
        assert result[0].verification_plan != ""

    def test_rich_sections_populated(self, mock_llm, sample_scored, fake_kg):
        slot = ExplainSlot(mock_llm)
        result = slot.explain([sample_scored], [], fake_kg)
        eh = result[0]
        assert eh.general_approach
        assert eh.actionable_now
        assert eh.why_it_matters
        assert eh.best_practices
        assert eh.novelty
        assert eh.risks
        assert eh.effect_cause_examples
        assert eh.section_citations["justification"] == ["chunk_001"]

    def test_explain_multiple_hypotheses(self, mock_llm, fake_kg):
        slot = ExplainSlot(mock_llm)
        scored_list = [
            ScoredHypothesis(
                hypothesis=Hypothesis(claim="Claim A", mechanism="Mech A",
                                      expected_effect="Effect A", evidence_refs=["chunk_001"]),
                score=0.9, features={"novelty": 0.5, "feasibility": 0.8, "effect": 0.9},
                cited_refs={"chunk_001": EvidenceChunk(chunk_id="chunk_001", doc_id="doc_1",
                                                       text="Evidence for A.", meta={})},
            ),
            ScoredHypothesis(
                hypothesis=Hypothesis(claim="Claim B", mechanism="Mech B",
                                      expected_effect="Effect B", evidence_refs=["chunk_002"]),
                score=0.7, features={"novelty": 0.3, "feasibility": 0.7, "effect": 0.6},
                cited_refs={"chunk_002": EvidenceChunk(chunk_id="chunk_002", doc_id="doc_2",
                                                       text="Evidence for B.", meta={})},
            ),
        ]
        result = slot.explain(scored_list, [], fake_kg)
        assert len(result) == 2
        assert result[0].scored == scored_list[0]
        assert result[1].scored == scored_list[1]

    def test_kg_neighbourhood_populated(self, mock_llm, sample_scored, fake_kg):
        slot = ExplainSlot(mock_llm)
        result = slot.explain([sample_scored], [], fake_kg)
        assert len(result[0].graph_neighbourhood) > 0
        assert any("Material" in line or "Property" in line or "influences" in line
                   for line in result[0].graph_neighbourhood)

    def test_llm_failure_fallback(self, sample_scored, fake_kg):
        llm = MagicMock()
        llm.with_structured_output.side_effect = RuntimeError("no structured")
        llm.invoke.side_effect = RuntimeError("LLM unavailable")
        slot = ExplainSlot(llm)
        result = slot.explain([sample_scored], [], fake_kg)
        assert len(result) == 1
        assert "не было сгенерировано" in result[0].justification
        assert result[0].uncertainty == "не удалось сгенерировать"
        assert result[0].verification_plan == "не удалось сгенерировать"

    def test_empty_ranked_list(self, mock_llm, fake_kg):
        slot = ExplainSlot(mock_llm)
        assert slot.explain([], [], fake_kg) == []

    def test_evidence_map_as_dict(self, mock_llm, sample_scored, fake_kg):
        slot = ExplainSlot(mock_llm)
        evidence_dict = {
            "chunk_001": EvidenceChunk(chunk_id="chunk_001", doc_id="doc_1",
                                       text="Xanthate collectors improve gold flotation.", meta={}),
        }
        result = slot.explain([sample_scored], evidence_dict, fake_kg)
        assert len(result) == 1
        assert result[0].justification != ""

    def test_external_web_source_cited(self, sample_scored, fake_kg):
        output = _full_output(cite="web:abc123")
        slot = ExplainSlot(_structured_llm(output))
        web = EvidenceChunk(chunk_id="web:abc123", doc_id="web:abc123",
                            text="Best practice article.",
                            meta={"url": "https://example.com/x", "source": "web"})
        result = slot.explain([sample_scored], [], fake_kg, external=[web])
        eh = result[0]
        assert "web:abc123" in eh.scored.cited_refs
        assert "https://example.com/x" in eh.external_urls

    def test_trace_recording(self, mock_llm, sample_scored, fake_kg):
        slot = ExplainSlot(mock_llm)
        trace = TraceRecord(run_id="test_run", stage="explain")
        result = slot.explain([sample_scored], [], fake_kg, trace=trace)
        assert len(result) == 1
        assert trace.token_in > 0
        assert trace.token_out > 0
        assert trace.latency_ms >= 0

    def test_trace_records_on_failure(self, sample_scored, fake_kg):
        llm = MagicMock()
        llm.with_structured_output.side_effect = RuntimeError("no structured")
        llm.invoke.side_effect = RuntimeError("LLM down")
        slot = ExplainSlot(llm)
        trace = TraceRecord(run_id="test_run", stage="explain")
        result = slot.explain([sample_scored], [], fake_kg, trace=trace)
        assert len(result) == 1
        assert trace.token_in > 0
        assert trace.token_out == 0
        assert trace.latency_ms >= 0
