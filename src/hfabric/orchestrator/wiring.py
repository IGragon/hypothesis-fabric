from __future__ import annotations

import os
from typing import Any

from hfabric.config import MVPConfig
from hfabric.contracts import (
    CitationProtocol,
    ExplanationProtocol,
    ExportProtocol,
    GeneratorProtocol,
    KGProtocol,
    RetrieverProtocol,
    ScorerProtocol,
)
from hfabric.embeddings import SentenceTransformersProvider
from hfabric.etl import ETL
from hfabric.explain.citation_bind import bind_claims
from hfabric.explain.explain_slot import ExplainSlot
from hfabric.export.writer import write_export
from hfabric.generator.synth import CandidateSynthesizer
from hfabric.kg.client import MemgraphKG
from hfabric.llm import create_chat_model
from hfabric.obs.traces import TraceCollector
from hfabric.orchestrator import Orchestrator
from hfabric.retriever import Retriever
from hfabric.scorer import Scorer
from hfabric.schemas import (
    EvidenceChunk,
    Hypothesis,
    RunResult,
    ScoredHypothesis,
)
from hfabric.storage.session_store import SessionStore


class _CitationAdapter:
    def bind(
        self,
        hypotheses: list[Hypothesis],
        chunks: dict[str, EvidenceChunk],
    ) -> tuple[list[ScoredHypothesis], float]:
        return bind_claims(hypotheses, chunks)


class _ExportAdapter:
    def export(self, result: RunResult, session_id: str) -> tuple[str, str]:
        return write_export(result, session_id)


def build_real_orchestrator(
    config: MVPConfig,
    *,
    session_id: str = "",
    llm: Any = None,
    kg: KGProtocol | None = None,
    embeddings: Any = None,
    store: SessionStore | None = None,
    retriever: RetrieverProtocol | None = None,
    generator: GeneratorProtocol | None = None,
    citation: CitationProtocol | None = None,
    scorer: ScorerProtocol | None = None,
    explanation: ExplanationProtocol | None = None,
    exporter: ExportProtocol | None = None,
    trace_collector: TraceCollector | None = None,
) -> Orchestrator:
    if llm is None:
        llm = create_chat_model(config.provider, config.model)

    if kg is None:
        kg = MemgraphKG(config.memgraph_uri)

    if embeddings is None:
        embeddings = SentenceTransformersProvider(config.embeddings_model)

    if store is None:
        db_path = (
            os.path.join("sessions", session_id, "session.db")
            if session_id
            else ":memory:"
        )
        store = SessionStore(db_path)

    if trace_collector is None:
        trace_collector = TraceCollector(store)

    if retriever is None:
        retriever = Retriever(embeddings, kg, config)

    if generator is None:
        generator = CandidateSynthesizer(llm, config)

    if citation is None:
        citation = _CitationAdapter()

    if scorer is None:
        scorer = Scorer(kg, config)

    if explanation is None:
        explanation = ExplainSlot(llm)

    if exporter is None:
        exporter = _ExportAdapter()

    return Orchestrator(
        llm=llm,
        retriever=retriever,
        generator=generator,
        citation=citation,
        scorer=scorer,
        explanation=explanation,
        exporter=exporter,
        kg=kg,
        store=store,
        trace_collector=trace_collector,
        config=config,
    )
