from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from hfabric.config import MVPConfig
from hfabric.contracts import KGProtocol
from hfabric.schemas import EvidenceChunk, Hypothesis, KPIParsed, ScoredHypothesis
from hfabric.scorer.features import (
    extract_effect,
    extract_feasibility,
    extract_novelty,
    extract_realizability,
    extract_risk,
)
from hfabric.scorer.calibration import apply_feedback_weights
from hfabric.scorer.constraint import constraint_check
from hfabric.scorer.ranker import WeightedRanker

if TYPE_CHECKING:
    from hfabric.scorer.llm_judge import LLMJudge
    from hfabric.storage.feedback_store import FeedbackStore

_log = logging.getLogger("hfabric.scorer")


class Scorer:
    def __init__(
        self,
        kg: KGProtocol,
        config: MVPConfig,
        llm_judge: LLMJudge | None = None,
        feedback_store: FeedbackStore | None = None,
    ) -> None:
        self.kg = kg
        self.config = config
        self._llm_judge = llm_judge
        base_weights = {
            "novelty": config.weight_novelty,
            "feasibility": config.weight_feasibility,
            "effect": config.weight_effect,
            "risk": config.weight_risk,
            "realizability": config.weight_realizability,
            "evidence": getattr(config, "weight_evidence", 0.10),
            "violation": getattr(config, "weight_violation", 0.15),
        }
        calibrated = apply_feedback_weights(feedback_store, base_weights)
        self.feedback_weights = calibrated
        self.ranker = WeightedRanker(weights=calibrated)

    def score(
        self,
        hypotheses: list[Hypothesis],
        chunks: dict[str, EvidenceChunk],
        kpi: KPIParsed,
        kg: KGProtocol,
        config: MVPConfig,
    ) -> list[ScoredHypothesis]:
        evidence_list = list(chunks.values())
        entries: list[dict] = []
        for hyp in hypotheses:
            check = constraint_check(hyp, kpi.constraints)
            violations = len(check.get("violations", []))
            evidence_refs = set(hyp.evidence_refs or [])
            evidence_count = sum(1 for r in evidence_refs if r in chunks)
            coverage = (evidence_count / max(1, len(evidence_refs))) if evidence_refs else 0.0
            features: dict[str, float] = {
                "novelty": extract_novelty(hyp, kg),
                "feasibility": extract_feasibility(hyp, kpi.constraints),
                "effect": extract_effect(hyp, kpi),
                "risk": extract_risk(hyp, self.kg),
                "realizability": extract_realizability(hyp, kpi.constraints),
                "evidence_count": float(evidence_count),
                "violation_count": float(violations),
                "coverage": float(coverage),
            }
            entries.append({"hypothesis": hyp, "features": features})

        if self._llm_judge is not None:
            for entry in entries:
                hyp = entry["hypothesis"]
                evidence = evidence_list[:5]
                llm_scores = self._llm_judge.judge(hyp, evidence, kpi)
                if llm_scores is not None:
                    det = entry["features"]
                    llm = llm_scores.to_dict()
                    entry["features"]["novelty"] = (det.get("novelty", 0) + llm.get("novelty", 0)) / 2
                    entry["features"]["feasibility"] = (det.get("feasibility", 0) + llm.get("feasibility", 0)) / 2
                    entry["features"]["effect"] = (det.get("effect", 0) + llm.get("effect", 0)) / 2
                    entry["features"]["risk"] = llm.get("risk", 0)

        if _log.isEnabledFor(logging.DEBUG):
            for entry in entries:
                f = entry["features"]
                _log.debug(
                    "features: %s feas=%.2f effect=%.2f ev=%s viol=%s cov=%.2f",
                    entry["hypothesis"].claim[:40],
                    f.get("feasibility", 0), f.get("effect", 0),
                    f.get("evidence_count", 0), f.get("violation_count", 0),
                    f.get("coverage", 0),
                )

        return self.ranker.rank(entries)
