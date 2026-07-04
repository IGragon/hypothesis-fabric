from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from hfabric.schemas import EvidenceChunk, Hypothesis, KPIParsed


@dataclass
class JudgeScores:
    novelty: float
    feasibility: float
    effect: float
    risk: float

    def to_dict(self) -> dict[str, float]:
        return {
            "novelty": self.novelty,
            "feasibility": self.feasibility,
            "effect": self.effect,
            "risk": self.risk,
        }


class LLMJudge:
    def __init__(self, llm: Any) -> None:
        self._llm = llm

    def judge(
        self,
        hypothesis: Hypothesis,
        evidence: list[EvidenceChunk],
        kpi: KPIParsed,
    ) -> JudgeScores | None:
        evidence_text = "\n".join(
            f"[{c.chunk_id}] {c.text[:200]}" for c in evidence[:5]
        )

        prompt = (
            f"Goal: {kpi.goal}\n"
            f"Target KPI: {kpi.kpi.metric}\n\n"
            f"Hypothesis: {hypothesis.claim}\n"
            f"Mechanism: {hypothesis.mechanism}\n"
            f"Expected Effect: {hypothesis.expected_effect}\n\n"
            f"Evidence:\n{evidence_text}\n\n"
            f"Score this hypothesis on 4 axes (0.0 to 1.0):\n"
            f"- novelty: how novel/original is this approach?\n"
            f"- feasibility: how practical/easy to implement?\n"
            f"- effect: expected magnitude of impact on the KPI\n"
            f"- risk: risk level (0=low risk, 1=high risk)\n\n"
            f'Return ONLY valid JSON: {{"novelty": 0.X, "feasibility": 0.X, "effect": 0.X, "risk": 0.X}}'
        )

        try:
            response = self._llm.invoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)
            if isinstance(content, list):
                content = "".join(
                    item.get("text", "") if isinstance(item, dict) else str(item)
                    for item in content
                )

            parsed = json.loads(content)

            scores = JudgeScores(
                novelty=float(parsed.get("novelty", 0.5)),
                feasibility=float(parsed.get("feasibility", 0.5)),
                effect=float(parsed.get("effect", 0.5)),
                risk=float(parsed.get("risk", 0.5)),
            )
            return self._validate(scores)
        except Exception:
            return None

    def _validate(self, scores: JudgeScores) -> JudgeScores:
        scores.novelty = max(0.0, min(1.0, scores.novelty))
        scores.feasibility = max(0.0, min(1.0, scores.feasibility))
        scores.effect = max(0.0, min(1.0, scores.effect))
        scores.risk = max(0.0, min(1.0, scores.risk))
        return scores
