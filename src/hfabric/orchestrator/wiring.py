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
from hfabric.export.csv_writer import write_csv
from hfabric.export.docx_writer import write_docx
from hfabric.export.pdf_writer import write_pdf
from hfabric.export.writer import write_export
from hfabric.generator.synth import CandidateSynthesizer
from hfabric.kg.client import MemgraphKG
from hfabric.kg.schema import load_schema
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
from hfabric.storage.feedback_store import FeedbackStore
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


class _DocxExportAdapter:
    def export(self, result: RunResult, session_id: str) -> str:
        return write_docx(result, session_id)


class _PdfExportAdapter:
    def export(self, result: RunResult, session_id: str) -> str:
        return write_pdf(result, session_id)


class _CsvExportAdapter:
    def export(self, result: RunResult, session_id: str) -> str:
        return write_csv(result, session_id)


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
        llm = create_chat_model(config.provider, config.model, temperature=config.temperature)

    if kg is None:
        kg_schema = load_schema(getattr(config, "kg_schema_path", None))
        try:
            kg = MemgraphKG(
                config.memgraph_uri,
                node_labels=kg_schema.node_labels,
                edge_types=kg_schema.edge_types,
            )
        except Exception:
            kg = None

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
        retriever = Retriever(embeddings, kg, config, llm=llm)

    if generator is None:
        generator = CandidateSynthesizer(llm, config)

    if citation is None:
        citation = _CitationAdapter()

    if scorer is None:
        feedback_store = None
        if session_id:
            fb_path = os.path.join("sessions", session_id, "feedback.db")
            if os.path.isfile(fb_path):
                feedback_store = FeedbackStore(fb_path)
        scorer = Scorer(kg, config, feedback_store=feedback_store)

    if explanation is None:
        per_hyp_timeout = getattr(config, "timeout_explain_per_hypothesis", None)
        if per_hyp_timeout is None:
            per_hyp_timeout = getattr(config, "timeout_explain", 120) / max(1, getattr(config, "max_explain_hypotheses", 3))
        explanation = ExplainSlot(
            llm,
            timeout_seconds=per_hyp_timeout,
            use_structured_output=getattr(config, "explain_use_structured_output", True),
            workers=getattr(config, "explain_workers", 3),
        )

    if exporter is None:
        if config.export_format == "docx":
            exporter = _DocxExportAdapter()
        elif config.export_format == "pdf":
            exporter = _PdfExportAdapter()
        elif config.export_format == "csv":
            exporter = _CsvExportAdapter()
        else:
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
