from __future__ import annotations

import pytest

from hfabric.obs.evals import (
    citation_existence_check,
    constraint_pass_check,
    jaccard_at_10,
    run_evals,
    schema_validity_check,
)
from hfabric.schemas import EvidenceChunk, Hypothesis, ScoredHypothesis


def _make_h(claim: str) -> Hypothesis:
    return Hypothesis(
        claim=claim,
        mechanism="A mechanism that works",
        expected_effect="Better recovery",
        evidence_refs=["ref_1"],
    )


def _make_sh(h: Hypothesis, refs: list[str] | None = None) -> ScoredHypothesis:
    refs = refs or h.evidence_refs
    return ScoredHypothesis(
        hypothesis=h,
        score=0.5,
        features={},
        cited_refs={
            r: EvidenceChunk(
                chunk_id=r, doc_id="d1", text="evidence", meta={}
            )
            for r in refs
        },
    )


class TestJaccardAt10:
    def test_identical_lists_returns_one(self) -> None:
        run_a = [_make_h(f"Claim {i}") for i in range(5)]
        run_b = [_make_h(f"Claim {i}") for i in range(5)]
        result = jaccard_at_10(run_a, run_b)
        assert result == 1.0

    def test_disjoint_lists_returns_zero(self) -> None:
        run_a = [_make_h("Xanthate collector improves gold flotation")]
        run_b = [_make_h("Completely unrelated claim about nickel smelting")]
        result = jaccard_at_10(run_a, run_b)
        assert result == 0.0

    def test_partial_overlap_correct_fraction(self) -> None:
        run_a = [
            _make_h("Xanthate collector increases Au recovery"),
            _make_h("New collector completely unrelated"),
        ]
        run_b = [
            _make_h("Xanthate collector increases Au recovery"),
            _make_h("Totally different smelting approach"),
        ]
        result = jaccard_at_10(run_a, run_b)
        assert result == pytest.approx(1 / 3, abs=0.01)

    def test_empty_lists_returns_one(self) -> None:
        assert jaccard_at_10([], []) == 1.0

    def test_one_empty_returns_zero(self) -> None:
        run_a = [_make_h("Something")]
        assert jaccard_at_10(run_a, []) == 0.0

    def test_fuzzy_match_threshold(self) -> None:
        run_a = [
            _make_h("Xanthate collector addition increases Au recovery by 5 percent")
        ]
        run_b = [
            _make_h("xanthate collector addition increases au recovery by 5 percent")
        ]
        result = jaccard_at_10(run_a, run_b)
        assert result == 1.0


class TestSchemaValidityCheck:
    def test_valid_hypotheses_pass(self) -> None:
        hs = [
            Hypothesis(
                claim="A valid claim with enough chars",
                mechanism="A valid mechanism long enough",
                expected_effect="Some effect",
                evidence_refs=["r1"],
            )
        ]
        result = schema_validity_check(hs)
        assert result["passed"] is True
        assert result["failed_count"] == 0
        assert result["violations"] == []

    def test_flags_empty_claim(self) -> None:
        hs = [
            Hypothesis(
                claim="",
                mechanism="Valid mechanism long enough",
                expected_effect="Effect",
                evidence_refs=["r1"],
            )
        ]
        result = schema_validity_check(hs)
        assert result["passed"] is False
        assert "claim empty" in result["violations"][0]

    def test_flags_short_claim(self) -> None:
        hs = [
            Hypothesis(
                claim="short",
                mechanism="Valid mechanism long enough",
                expected_effect="Effect",
                evidence_refs=["r1"],
            )
        ]
        result = schema_validity_check(hs)
        assert result["passed"] is False
        assert "claim empty or <= 10 chars" in result["violations"][0]

    def test_flags_empty_mechanism(self) -> None:
        hs = [
            Hypothesis(
                claim="A valid claim goes here",
                mechanism="",
                expected_effect="Effect",
                evidence_refs=["r1"],
            )
        ]
        result = schema_validity_check(hs)
        assert result["passed"] is False
        assert "mechanism empty" in str(result["violations"])

    def test_flags_empty_expected_effect(self) -> None:
        hs = [
            Hypothesis(
                claim="A valid claim goes here",
                mechanism="Valid mechanism long enough",
                expected_effect="",
                evidence_refs=["r1"],
            )
        ]
        result = schema_validity_check(hs)
        assert result["passed"] is False
        assert "expected_effect empty" in str(result["violations"])

    def test_flags_empty_evidence_refs(self) -> None:
        hs = [
            Hypothesis(
                claim="A valid claim goes here",
                mechanism="Valid mechanism long enough",
                expected_effect="Effect",
                evidence_refs=[],
            )
        ]
        result = schema_validity_check(hs)
        assert result["passed"] is False
        assert "evidence_refs empty" in str(result["violations"])

    def test_failed_count_correct(self) -> None:
        hs = [
            Hypothesis(
                claim="",
                mechanism="",
                expected_effect="Effect",
                evidence_refs=["r1"],
            ),
            Hypothesis(
                claim="Good claim here yes",
                mechanism="Good mechanism text here",
                expected_effect="Effect",
                evidence_refs=["r2"],
            ),
        ]
        result = schema_validity_check(hs)
        assert result["failed_count"] == 1


class TestCitationExistenceCheck:
    def test_full_coverage(self) -> None:
        h = _make_h("Claim")
        sh = _make_sh(h, refs=["ref_1"])
        result = citation_existence_check([sh])
        assert result["passed"] is True
        assert result["coverage"] == 1.0
        assert result["total_refs"] == 1
        assert result["matched_refs"] == 1

    def test_partial_coverage(self) -> None:
        h = Hypothesis(
            claim="Claim",
            mechanism="A mechanism long enough",
            expected_effect="Effect",
            evidence_refs=["ref_1", "ref_2", "ref_3"],
        )
        sh = _make_sh(h, refs=["ref_1", "ref_3"])
        result = citation_existence_check([sh])
        assert result["passed"] is False
        assert result["coverage"] == pytest.approx(2 / 3, abs=0.01)
        assert result["matched_refs"] == 2

    def test_no_hypotheses_zero_coverage(self) -> None:
        result = citation_existence_check([])
        assert result["passed"] is True
        assert result["coverage"] == 0.0
        assert result["total_refs"] == 0


class TestConstraintPassCheck:
    def test_all_pass(self) -> None:
        hs = [_make_h("Using xanthate for recovery")]
        constraints = ["must use xanthate"]
        result = constraint_pass_check(hs, constraints)
        assert result["passed"] is True
        assert result["pass_count"] == 1
        assert result["total"] == 1
        assert result["pass_rate"] == 1.0

    def test_none_pass(self) -> None:
        hs = [_make_h("Using xanthate for recovery")]
        constraints = ["must use cyanide"]
        result = constraint_pass_check(hs, constraints)
        assert result["passed"] is False
        assert result["pass_count"] == 0

    def test_negation_violated_if_positive_indicator_found(self) -> None:
        hs = [_make_h("increase cyanide usage for better results")]
        constraints = ["no cyanide increase"]
        result = constraint_pass_check(hs, constraints)
        assert result["pass_count"] == 0

    def test_negation_passes_if_no_positive_indicator(self) -> None:
        hs = [_make_h("maintain cyanide at current levels")]
        constraints = ["no cyanide increase"]
        result = constraint_pass_check(hs, constraints)
        assert result["pass_count"] == 1

    def test_no_constraints_all_pass(self) -> None:
        hs = [_make_h("Any claim")]
        result = constraint_pass_check(hs, [])
        assert result["passed"] is True


class TestRunEvals:
    def test_produces_complete_report_dict(self) -> None:
        h = Hypothesis(
            claim="Xanthate collector improves Au recovery",
            mechanism="Xanthates chemisorb on gold surfaces increasing hydrophobicity",
            expected_effect="+5-10% Au recovery",
            evidence_refs=["chunk_001"],
        )
        result = run_evals(
            session_id="sess-1",
            hypotheses=[h],
            constraints=["no cyanide increase"],
        )
        assert result["session_id"] == "sess-1"
        assert "schema_validity" in result
        assert "constraint_pass" in result
        assert "citation_existence" not in result
        assert result["schema_validity"]["passed"] is True

    def test_includes_citation_existence_for_scored(self) -> None:
        h = _make_h("Claim")
        sh = _make_sh(h, refs=["ref_1"])
        result = run_evals(session_id="sess-2", hypotheses=[sh])
        assert "citation_existence" in result
        assert result["citation_existence"]["coverage"] == 1.0

    def test_omits_constraints_when_none(self) -> None:
        h = _make_h("Claim")
        result = run_evals(session_id="sess-3", hypotheses=[h])
        assert "constraint_pass" not in result
