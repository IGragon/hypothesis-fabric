from __future__ import annotations

from hfabric.retriever.budget import count_tokens, truncate_to_budget
from hfabric.schemas import EvidenceChunk


class BudgetEnforcer:
    def __init__(self, budget_tokens: int = 16000):
        self._budget = budget_tokens

    def truncate_evidence(
        self, evidence: list[EvidenceChunk]
    ) -> list[EvidenceChunk]:
        return truncate_to_budget(evidence, self._budget)

    def truncate_text(self, text: str) -> str:
        token_count = count_tokens(text)
        if token_count <= self._budget:
            return text
        ratio = self._budget / token_count
        max_chars = int(len(text) * ratio * 0.9)
        return text[:max_chars] + "\n...[truncated]"

    @property
    def budget(self) -> int:
        return self._budget
