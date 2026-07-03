from __future__ import annotations

import re


def _token_to_word_count(token_count: int) -> int:
    return max(1, int(token_count / 1.3))


def _split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _split_words(text: str) -> list[str]:
    return text.split()


def _recursive_split(text: str, chunk_words: int, depth: int = 0) -> list[str]:
    if depth == 0:
        segments = _split_paragraphs(text)
    elif depth == 1:
        segments = _split_sentences(text)
    else:
        words = _split_words(text)
        return [" ".join(words[i : i + chunk_words]) for i in range(0, len(words), chunk_words)]

    result: list[str] = []
    for seg in segments:
        word_count = len(seg.split())
        if word_count <= chunk_words:
            result.append(seg)
        else:
            result.extend(_recursive_split(seg, chunk_words, depth + 1))
    return result


def chunk_document(text: str, chunk_size: int = 512, overlap: int = 64) -> list[dict]:
    chunk_words = _token_to_word_count(chunk_size)
    overlap_words = _token_to_word_count(overlap)
    step = max(1, chunk_words - overlap_words)

    all_words = text.split()

    chunks: list[dict] = []

    if not all_words:
        return chunks

    start_word = 0
    while start_word < len(all_words):
        end_word = min(start_word + chunk_words, len(all_words))
        chunk_text = " ".join(all_words[start_word:end_word])

        prefix = " ".join(all_words[:start_word])
        start_char = len(prefix) + 1 if prefix else 0
        end_char = len(" ".join(all_words[:end_word]))

        chunk_id = f"chunk_{len(chunks):04d}"

        chunks.append({
            "text": chunk_text,
            "chunk_id": chunk_id,
            "start": start_char,
            "end": end_char,
        })

        if end_word >= len(all_words):
            break
        start_word += step

    return chunks
