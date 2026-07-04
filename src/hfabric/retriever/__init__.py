from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hfabric.config import MVPConfig
from hfabric.contracts import KGProtocol
from hfabric.embeddings import EmbeddingsProvider
from hfabric.retriever.budget import truncate_to_budget
from hfabric.retriever.kg_retrieval import retrieve_kg_evidence
from hfabric.retriever.query_plan import build_query_plan
from hfabric.retriever.rerank import rerank_evidence
from hfabric.retriever.vector import merge_results, query_faiss
from hfabric.schemas import EvidenceChunk, KPIParsed


@dataclass
class RetrieveResult:
    evidence: list[EvidenceChunk] = field(default_factory=list)
    low_confidence: bool = False


class Retriever:
    def __init__(
        self,
        embeddings: EmbeddingsProvider,
        kg: KGProtocol,
        config: MVPConfig,
        llm: Any = None,
    ):
        self._embeddings = embeddings
        self._kg = kg
        self._config = config
        self._llm = llm

    def retrieve(
        self,
        kpi: KPIParsed,
        config: MVPConfig | None = None,
        session_id: str = "",
    ) -> dict:
        cfg = config or self._config

        plan = build_query_plan(kpi)

        query_vector = self._embeddings.embed(
            [plan["query_text"]], prefix=""
        )[0]

        kb_dir = "knowledge_base/.index/kb"
        session_dir = f"sessions/{session_id}/index" if session_id else None

        kb_results = query_faiss(kb_dir, query_vector, cfg.vector_top_k)

        session_results: list[EvidenceChunk] = []
        if session_dir:
            try:
                session_results = query_faiss(
                    session_dir, query_vector, cfg.vector_top_k
                )
            except Exception:
                session_results = []

        merged = merge_results(kb_results, session_results)

        chunks_by_id = {c.chunk_id: c for c in merged}

        kg_chunks = retrieve_kg_evidence(
            self._kg, plan["kg_entities"], chunks_by_id, cfg.kg_hops
        )

        kg_ids = {c.chunk_id for c in kg_chunks}
        for kg_chunk in kg_chunks:
            chunks_by_id[kg_chunk.chunk_id] = kg_chunk

        all_evidence = list(merged)
        for kg_chunk in kg_chunks:
            if kg_chunk.chunk_id not in {c.chunk_id for c in all_evidence}:
                all_evidence.append(kg_chunk)

        if not all_evidence:
            return {"evidence": [], "low_confidence": True}

        if self._llm is None:
            raise RuntimeError(
                "Retriever requires an LLM via constructor injection; "
                "pass llm=... to Retriever (dependency injection)."
            )
        llm = self._llm

        reranked, low_confidence = rerank_evidence(
            all_evidence, kpi.goal, llm, cfg.rerank_top_k, cfg.fe1_max_query_expansion
        )

        truncated = truncate_to_budget(reranked, cfg.context_budget_tokens)

        return {
            "evidence": truncated,
            "low_confidence": low_confidence,
        }
