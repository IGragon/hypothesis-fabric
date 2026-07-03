from __future__ import annotations

from hfabric.config import MVPConfig
from hfabric.contracts import KGProtocol
from hfabric.schemas import EvidenceChunk, Hypothesis, KPIParsed, ScoredHypothesis
from hfabric.scorer.features import extract_effect, extract_feasibility, extract_novelty
from hfabric.scorer.ranker import WeightedRanker


class Scorer:
    def __init__(self, kg: KGProtocol, config: MVPConfig) -> None:
        self.kg = kg
        self.config = config
        self.ranker = WeightedRanker(
            weights={
                "novelty": config.weight_novelty,
                "feasibility": config.weight_feasibility,
                "effect": config.weight_effect,
            }
        )

    def score(
        self,
        hypotheses: list[Hypothesis],
        chunks: dict[str, EvidenceChunk],
        kpi: KPIParsed,
        kg: KGProtocol,
        config: MVPConfig,
    ) -> list[ScoredHypothesis]:
        entries: list[dict] = []
        for hyp in hypotheses:
            features: dict[str, float] = {
                "novelty": extract_novelty(hyp, kg),
                "feasibility": extract_feasibility(hyp, kpi.constraints),
                "effect": extract_effect(hyp, kpi),
            }
            entries.append({"hypothesis": hyp, "features": features})

        return self.ranker.rank(entries)
