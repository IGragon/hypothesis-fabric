from __future__ import annotations

import json
import re

from hfabric.schemas import EvidenceChunk

_FE1_TOKEN_THRESHOLD = 500
_JSON_ARRAY_PATTERN = re.compile(r"\[.*\]", re.DOTALL)


def _build_rerank_prompt(evidence: list[EvidenceChunk], goal: str) -> str:
    lines = [
        "You are a scientific evidence reranker. Given a research goal and a list of evidence chunks,",
        "rank the chunks by their relevance to the goal. Return a JSON array of chunk_ids in descending",
        "order of relevance (most relevant first).",
        "",
        f"Goal: {goal}",
        "",
        "Evidence chunks:",
    ]
    for i, chunk in enumerate(evidence):
        lines.append(f"  [{chunk.chunk_id}] {chunk.text}")

    lines.append("")
    lines.append("Output ONLY a JSON array of chunk_ids, e.g. [\"chunk_003\", \"chunk_001\", \"chunk_002\"].")
    return "\n".join(lines)


def _count_total_tokens(evidence: list[EvidenceChunk]) -> int:
    from hfabric.retriever.budget import count_tokens

    total = 0
    for chunk in evidence:
        total += count_tokens(chunk.text)
    return total


def _parse_rerank_response(
    response_text: str,
    evidence_map: dict[str, EvidenceChunk],
    original_order: list[EvidenceChunk],
) -> list[EvidenceChunk]:
    match = _JSON_ARRAY_PATTERN.search(response_text)
    if not match:
        return list(original_order)

    try:
        ranked_ids = json.loads(match.group(0))
        if not isinstance(ranked_ids, list):
            return list(original_order)
    except json.JSONDecodeError:
        return list(original_order)

    seen: set[str] = set()
    reranked: list[EvidenceChunk] = []
    for cid in ranked_ids:
        if cid in evidence_map and cid not in seen:
            seen.add(cid)
            reranked.append(evidence_map[cid])

    for chunk in original_order:
        if chunk.chunk_id not in seen:
            seen.add(chunk.chunk_id)
            reranked.append(chunk)

    return reranked


def rerank_evidence(
    evidence: list[EvidenceChunk],
    goal: str,
    llm,
    top_k: int = 8,
    max_expansions: int = 2,
) -> tuple[list[EvidenceChunk], bool]:
    if not evidence:
        return [], True

    evidence_map = {c.chunk_id: c for c in evidence}
    original_order = list(evidence)

    for expansion in range(max_expansions + 1):
        prompt = _build_rerank_prompt(evidence, goal)

        try:
            response = llm.invoke(prompt)
            response_text = response.content if hasattr(response, "content") else str(response)
        except Exception:
            reranked = list(evidence)
        else:
            reranked = _parse_rerank_response(
                str(response_text), evidence_map, evidence
            )

        total_tokens = _count_total_tokens(reranked)
        low_confidence = total_tokens < _FE1_TOKEN_THRESHOLD

        if not low_confidence or expansion >= max_expansions:
            limited = reranked[:top_k]
            return limited, low_confidence

    limited = evidence[:top_k]
    return limited, True
