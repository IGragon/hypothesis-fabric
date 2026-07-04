from __future__ import annotations

import re

from hfabric.schemas import EvidenceChunk, Hypothesis, ScoredHypothesis


def _is_cyrillic(text: str) -> bool:
    return bool(re.search(r"[\u0400-\u04FF]", text))


def bind_claims(
    hypotheses: list[Hypothesis],
    chunks_map: dict[str, EvidenceChunk],
    threshold: float = 55.0,
) -> tuple[list[ScoredHypothesis], float]:
    if not hypotheses:
        return ([], 0.0)

    total_refs = 0
    total_matched = 0
    scored: list[ScoredHypothesis] = []

    for hyp in hypotheses:
        cited_refs: dict[str, EvidenceChunk] = {}
        unique_refs = list(dict.fromkeys(hyp.evidence_refs))
        ref_count = len(unique_refs)
        total_refs += ref_count
        matched = 0

        for chunk_id in unique_refs:
            chunk = chunks_map.get(chunk_id)
            if chunk is None:
                continue
            cited_refs[chunk_id] = chunk
            matched += 1

        total_matched += matched

        scored.append(
            ScoredHypothesis(
                hypothesis=hyp,
                score=0.0,
                features={},
                cited_refs=cited_refs,
            )
        )

    coverage = total_matched / total_refs if total_refs > 0 else 0.0
    return (scored, coverage)
