from __future__ import annotations

import tiktoken

from hfabric.schemas import EvidenceChunk

_ENCODING = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_ENCODING.encode(text))


def truncate_to_budget(
    evidence: list[EvidenceChunk], budget_tokens: int = 16000
) -> list[EvidenceChunk]:
    if not evidence:
        return []

    result: list[EvidenceChunk] = []
    current_tokens = 0

    for chunk in evidence:
        chunk_tokens = count_tokens(chunk.text)
        if current_tokens + chunk_tokens <= budget_tokens:
            result.append(chunk)
            current_tokens += chunk_tokens
        else:
            break

    return result
