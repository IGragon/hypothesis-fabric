from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import faiss


def build_faiss(
    embeddings: list[list[float]],
    chunks: list[dict],
    index_dir: str,
) -> str:
    import faiss

    os.makedirs(index_dir, exist_ok=True)

    vectors = np.array(embeddings, dtype=np.float32)

    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    vectors = vectors / norms

    dim = vectors.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(vectors)

    faiss_path = os.path.join(index_dir, "faiss.bin")
    faiss.write_index(index, faiss_path)

    chunk_records = [
        {
            "chunk_id": c.get("chunk_id", ""),
            "doc_id": c.get("meta", {}).get("doc_id", ""),
            "text": c.get("text", ""),
            "meta": c.get("meta", {}),
        }
        for c in chunks
    ]
    chunks_path = os.path.join(index_dir, "chunks.json")
    with open(chunks_path, "w") as f:
        json.dump(chunk_records, f, ensure_ascii=False)

    return faiss_path


def load_faiss(index_dir: str) -> tuple:
    import faiss

    faiss_path = os.path.join(index_dir, "faiss.bin")
    index = faiss.read_index(faiss_path)

    chunks_path = os.path.join(index_dir, "chunks.json")
    with open(chunks_path) as f:
        chunks = json.load(f)

    return index, chunks


def index_exists(index_dir: str) -> bool:
    if not index_dir:
        return False
    faiss_path = os.path.join(index_dir, "faiss.bin")
    return os.path.isfile(faiss_path)


def get_raw_files_mtime(raw_files_dir: str) -> float:
    if not os.path.isdir(raw_files_dir):
        return 0.0

    max_mtime = 0.0
    for entry in os.scandir(raw_files_dir):
        if entry.is_file():
            mtime = entry.stat().st_mtime
            if mtime > max_mtime:
                max_mtime = mtime
    return max_mtime
