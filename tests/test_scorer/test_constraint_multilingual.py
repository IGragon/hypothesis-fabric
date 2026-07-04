from __future__ import annotations

from hfabric.schemas import Hypothesis
from hfabric.scorer.constraint import constraint_check


def _h(claim: str, mechanism: str = "Xanthate improves flotation", effect: str = "higher Au recovery") -> Hypothesis:
    return Hypothesis(claim=claim, mechanism=mechanism, expected_effect=effect, evidence_refs=["c1"])


class TestMultilingualConstraints:
    def test_russian_negation_violated_by_positive_context(self):
        h = _h("увеличение цианида повышает извлечение")
        r = constraint_check(h, ["без увеличения цианида"])
        assert r["ok"] is False
        assert any(" цианид" in v or "cyanide" in v for v in r["violations"])

    def test_russian_negation_passes_when_not_violated(self):
        h = _h("поддержание цианида на текущем уровне", mechanism="без изменений", effect="стабильное извлечение")
        r = constraint_check(h, ["без увеличения цианида"])
        assert r["ok"] is True

    def test_cross_script_negation_constraint_keyword_not_matched(self):
        h = _h("Increase cyanide to improve recovery")
        r = constraint_check(h, ["без увеличения цианида"])
        assert r["ok"] is True

    def test_availability_constraint_passes_russian(self):
        h = _h("xanthate only", mechanism="no cyanide", effect="recovery")
        r = constraint_check(h, ["доступное сырьё: ксантанат"])
        assert r["ok"] is True

    def test_positive_russian_constraint_enforced(self):
        h = _h("Используем ксантанат для флотации", mechanism="ксантанат", effect="извлечение")
        r = constraint_check(h, ["использовать ксантанат"])
        assert r["ok"] is True
        h2 = _h("Только цианид", mechanism="other", effect="other")
        r2 = constraint_check(h2, ["использовать ксантанат"])
        assert r2["ok"] is False

    def test_deterministic_multilingual(self):
        h = _h("увеличение цианида повышает извлечение")
        r1 = constraint_check(h, ["без увеличения цианида"])
        r2 = constraint_check(h, ["без увеличения цианида"])
        assert r1 == r2