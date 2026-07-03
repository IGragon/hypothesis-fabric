from __future__ import annotations

from hfabric.scorer.constraint import constraint_check
from hfabric.schemas import Hypothesis


class TestConstraintCheck:
    def test_no_violations_when_empty_constraints(self):
        hyp = Hypothesis(
            claim="test", mechanism="test", expected_effect="test", evidence_refs=[]
        )
        result = constraint_check(hyp, [])
        assert result["ok"] is True
        assert result["violations"] == []

    def test_negation_constraint_violated_by_positive_keyword(self):
        hyp = Hypothesis(
            claim="Increase cyanide to improve recovery",
            mechanism="Higher cyanide concentration increases gold dissolution",
            expected_effect="higher Au recovery",
            evidence_refs=[],
        )
        result = constraint_check(hyp, ["no cyanide increase"])
        assert result["ok"] is False
        assert len(result["violations"]) > 0
        assert any("cyanide" in v for v in result["violations"])

    def test_negation_constraint_passes_when_not_violated(self):
        hyp = Hypothesis(
            claim="Sodium sulphide pre-treatment without cyanide",
            mechanism="Sulphidization improves flotation without raising cyanide",
            expected_effect="improved flotation",
            evidence_refs=[],
        )
        result = constraint_check(hyp, ["no cyanide increase"])
        assert result["ok"] is True

    def test_positive_constraint_violated_when_keyword_missing(self):
        hyp = Hypothesis(
            claim="Something unrelated",
            mechanism="Different topic",
            expected_effect="no effect on recovery",
            evidence_refs=[],
        )
        result = constraint_check(hyp, ["increase Au recovery", "use xanthate"])
        assert result["ok"] is False
        assert len(result["violations"]) > 0

    def test_positive_constraint_passes_when_keywords_present(self):
        hyp = Hypothesis(
            claim="Xanthate collector improves Au recovery",
            mechanism="Better gold flotation through chemisorption",
            expected_effect="higher Au recovery rate",
            evidence_refs=[],
        )
        result = constraint_check(hyp, ["increase Au recovery", "use xanthate"])
        assert result["ok"] is True

    def test_multiple_constraints_mixed(self):
        hyp = Hypothesis(
            claim="Use xanthate to improve Au recovery",
            mechanism="Xanthate improves flotation",
            expected_effect="higher recovery",
            evidence_refs=[],
        )
        constraints = ["increase Au recovery", "no cyanide increase"]
        result = constraint_check(hyp, constraints)
        assert result["ok"] is True

    def test_returns_dict_with_correct_keys(self):
        hyp = Hypothesis(
            claim="test", mechanism="test", expected_effect="test", evidence_refs=[]
        )
        result = constraint_check(hyp, ["no cyanide"])
        assert "ok" in result
        assert "violations" in result
        assert isinstance(result["ok"], bool)
        assert isinstance(result["violations"], list)

    def test_deterministic_same_input(self):
        hyp = Hypothesis(
            claim="Increase cyanide to improve recovery",
            mechanism="Higher cyanide increases gold dissolution",
            expected_effect="higher Au recovery",
            evidence_refs=[],
        )
        r1 = constraint_check(hyp, ["no cyanide increase"])
        r2 = constraint_check(hyp, ["no cyanide increase"])
        assert r1 == r2
