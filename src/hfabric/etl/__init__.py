from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

import numpy as np

from hfabric.contracts import ETLProtocol, KGProtocol
from hfabric.embeddings import EmbeddingsProvider
from hfabric.schemas import IndexArtifact
from hfabric.etl.parser import SUPPORTED_EXTS, parse, structure_ocr_pages
from hfabric.etl.chunker import chunk_document
from hfabric.etl.faiss_index import build_faiss, index_exists, get_raw_files_mtime
from hfabric.etl.kg_build import extract_entities, extract_edges, detect_contradictions

if TYPE_CHECKING:
    from hfabric.config import MVPConfig


class ETL:
    def __init__(
        self,
        embeddings_provider: EmbeddingsProvider,
        kg: KGProtocol,
        config: "MVPConfig | None" = None,
        kg_patterns: dict | None = None,
    ):
        self._embeddings = embeddings_provider
        self._kg = kg
        self._config = config
        if kg_patterns is None and config is not None and getattr(config, "kg_schema_path", None):
            from hfabric.kg.schema import load_schema
            self._kg_patterns = load_schema(config.kg_schema_path).patterns
        else:
            self._kg_patterns = kg_patterns
        self._vision_model: Any = None
        self._vision_resolved = False

    def _get_vision_model(self):
        if self._vision_resolved:
            return self._vision_model
        self._vision_resolved = True
        if self._config is not None:
            try:
                from hfabric.llm import create_vision_chat_model

                self._vision_model = create_vision_chat_model(self._config)
            except Exception:
                self._vision_model = None
        return self._vision_model

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

        source_files = sorted(
            f for f in os.listdir(source_dir)
            if f.lower().endswith(SUPPORTED_EXTS)
        )

        vision_model = self._get_vision_model()
        all_pages: list[dict] = []
        for fname in source_files:
            fpath = os.path.join(source_dir, fname)
            try:
                all_pages.extend(parse(fpath, config=self._config, vision_model=vision_model))
            except Exception:
                continue

        all_chunks: list[dict] = []
        for page in all_pages:
            page_chunks = chunk_document(page["text"])
            for c in page_chunks:
                c["meta"] = page["meta"]
            all_chunks.extend(page_chunks)

        if self._config is not None and getattr(self._config, "enable_ocr_structuring", True):
            ocr_pages = [p for p in all_pages if p.get("meta", {}).get("image")]
            if ocr_pages:
                merged_ocr = "\n\n".join(
                    p["meta"].get("ocr_text", "") or p["text"]
                    for p in ocr_pages
                ).strip()
                if merged_ocr:
                    structured = structure_ocr_pages(
                        merged_ocr,
                        config=self._config,
                        timeout_seconds=getattr(self._config, "timeout_ocr_structure", 60),
                    )
                    if structured:
                        all_pages.append({
                            "text": structured,
                            "meta": {
                                "page": 1,
                                "path": "ocr_structured_report",
                                "doc_id": "ocr_structured_report",
                                "section": "Structured OCR Report",
                                "structured": True,
                            },
                        })
                        structured_chunks = chunk_document(structured)
                        for c in structured_chunks:
                            c["meta"] = all_pages[-1]["meta"]
                        all_chunks.extend(structured_chunks)

        texts = [c["text"] for c in all_chunks]
        embeddings = self._embeddings.embed(texts, prefix="passage: ")

        print(f"[hfabric.etl] building FAISS index for {len(all_chunks)} chunks", flush=True)
        faiss_path = build_faiss(embeddings, all_chunks, index_dir)
        print(f"[hfabric.etl] FAISS index built", flush=True)

        print(f"[hfabric.etl] extracting KG entities from {len(all_chunks)} chunks", flush=True)
        kg_entities: list[dict] = []
        for chunk in all_chunks:
            entities = extract_entities(chunk["text"], patterns=self._kg_patterns)
            for e in entities:
                e["provenance"] = {
                    "chunk_id": chunk["chunk_id"],
                    "doc_id": chunk.get("meta", {}).get("doc_id", ""),
                }
            kg_entities.extend(entities)

        print(f"[hfabric.etl] {len(kg_entities)} KG entities extracted, adding to Memgraph", flush=True)
        if kg_entities and self._kg is not None:
            try:
                self._kg.add_entities(kg_entities, session_id, source_kind)
                print(f"[hfabric.etl] KG entities added", flush=True)
            except Exception as e:
                print(f"[hfabric.etl] KG entities FAILED: {e}", flush=True)
        else:
            print(f"[hfabric.etl] skipping KG entities (kg={self._kg is not None}, entities={len(kg_entities)})", flush=True)

        print(f"[hfabric.etl] detecting contradictions and extracting edges", flush=True)
        contradictions = detect_contradictions(all_chunks)
        kg_edges = extract_edges(all_chunks, patterns=self._kg_patterns) + [
            {
                "from_label": "Source",
                "from_name": c["from_name"],
                "to_label": "Source",
                "to_name": c["to_name"],
                "rel_type": "contradicts",
                "provenance": {"entity": c.get("provenance", {}).get("entity", "")},
            }
            for c in contradictions
        ]
        print(f"[hfabric.etl] {len(kg_edges)} KG edges extracted, adding to Memgraph", flush=True)
        if kg_edges and self._kg is not None:
            try:
                self._kg.add_edges(kg_edges, session_id, source_kind)
                print(f"[hfabric.etl] KG edges added", flush=True)
            except Exception as e:
                print(f"[hfabric.etl] KG edges FAILED: {e}", flush=True)
        else:
            print(f"[hfabric.etl] skipping KG edges (kg={self._kg is not None}, edges={len(kg_edges)})", flush=True)

        print(f"[hfabric.etl] build_index DONE", flush=True)

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
