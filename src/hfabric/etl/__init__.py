from __future__ import annotations

import os
from typing import TYPE_CHECKING

import numpy as np

from hfabric.contracts import ETLProtocol, KGProtocol
from hfabric.embeddings import EmbeddingsProvider
from hfabric.schemas import IndexArtifact
from hfabric.etl.parser import parse_pdf
from hfabric.etl.chunker import chunk_document
from hfabric.etl.faiss_index import build_faiss, index_exists, get_raw_files_mtime
from hfabric.etl.kg_build import extract_entities, extract_edges


class ETL:
    def __init__(self, embeddings_provider: EmbeddingsProvider, kg: KGProtocol):
        self._embeddings = embeddings_provider
        self._kg = kg

    def build_index(
        self,
        source_dir: str,
        index_dir: str,
        session_id: str | None,
        source_kind: str,
    ) -> IndexArtifact:
        if self._is_fresh_enough(source_dir, index_dir):
            chunks_path = os.path.join(index_dir, "chunks.json")
            import json
            with open(chunks_path) as f:
                chunk_records = json.load(f)
            return IndexArtifact(
                index_dir=index_dir,
                faiss_path=os.path.join(index_dir, "faiss.bin"),
                chunks_path=chunks_path,
                num_chunks=len(chunk_records),
                source=source_dir,
                session_id=session_id,
            )

        pdf_files = sorted(
            f for f in os.listdir(source_dir)
            if f.lower().endswith(".pdf")
        )

        all_pages: list[dict] = []
        for pdf_file in pdf_files:
            pdf_path = os.path.join(source_dir, pdf_file)
            all_pages.extend(parse_pdf(pdf_path))

        all_chunks: list[dict] = []
        for page in all_pages:
            page_chunks = chunk_document(page["text"])
            for c in page_chunks:
                c["meta"] = page["meta"]
            all_chunks.extend(page_chunks)

        texts = [c["text"] for c in all_chunks]
        embeddings = self._embeddings.embed(texts, prefix="passage: ")

        faiss_path = build_faiss(embeddings, all_chunks, index_dir)

        kg_entities: list[dict] = []
        for chunk in all_chunks:
            entities = extract_entities(chunk["text"])
            for e in entities:
                e["provenance"] = {
                    "chunk_id": chunk["chunk_id"],
                    "doc_id": chunk.get("meta", {}).get("doc_id", ""),
                }
            kg_entities.extend(entities)

        if kg_entities:
            self._kg.add_entities(kg_entities, session_id, source_kind)

        kg_edges = extract_edges(all_chunks)
        if kg_edges:
            self._kg.add_edges(kg_edges, session_id, source_kind)

        return IndexArtifact(
            index_dir=index_dir,
            faiss_path=faiss_path,
            chunks_path=os.path.join(index_dir, "chunks.json"),
            num_chunks=len(all_chunks),
            source=source_dir,
            session_id=session_id,
        )

    def _is_fresh_enough(self, source_dir: str, index_dir: str) -> bool:
        if not index_exists(index_dir):
            return False
        source_mtime = get_raw_files_mtime(source_dir)
        index_mtime = get_raw_files_mtime(index_dir)
        return source_mtime <= index_mtime


__all__ = ["ETL"]
