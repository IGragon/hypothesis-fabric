from __future__ import annotations

from typing import Protocol

from hfabric.config import MVPConfig
from hfabric.schemas import (
    EvidenceChunk,
    ExplainedHypothesis,
    Hypothesis,
    IndexArtifact,
    KGNode,
    RunResult,
    ScoredHypothesis,
    TraceRecord,
)


class ETLProtocol(Protocol):
    def build_index(
        self,
        source_dir: str,
        index_dir: str,
        session_id: str | None,
        source_kind: str,
    ) -> IndexArtifact:
        ...


class KGProtocol(Protocol):
    def add_entities(
        self,
        entities: list[dict],
        session_id: str | None,
        source: str,
    ) -> None:
        ...

    def add_edges(
        self,
        edges: list[dict],
        session_id: str | None,
        source: str,
    ) -> None:
        ...

    def traverse(self, cypher: str, params: dict | None = None) -> list[KGNode]:
        ...

    def get_entities(self, name: str) -> list[KGNode]:
        ...

    def neighbours(self, node_id: str, hops: int = 2) -> list[KGNode]:
        ...

    def conflicts(self, source_id: str) -> list[KGNode]:
        ...

    def dump(self, path: str) -> None:
        ...

    def load(self, path: str) -> None:
        ...


class RetrieverProtocol(Protocol):
    def retrieve(
        self,
        kpi: ...,
        config: MVPConfig,
        session_id: str,
    ) -> list[EvidenceChunk]:
        ...


class GeneratorProtocol(Protocol):
    def generate(
        self,
        evidence: list[EvidenceChunk],
        kpi: ...,
        trace: TraceRecord | None = None,
    ) -> list[Hypothesis]:
        ...


class CitationProtocol(Protocol):
    def bind(
        self,
        hypotheses: list[Hypothesis],
        chunks: dict[str, EvidenceChunk],
    ) -> tuple[list[ScoredHypothesis], float]:
        ...


class ScorerProtocol(Protocol):
    def score(
        self,
        hypotheses: list[Hypothesis],
        chunks: dict[str, EvidenceChunk],
        kpi: ...,
        kg: KGProtocol,
        config: MVPConfig,
    ) -> list[ScoredHypothesis]:
        ...


class ExplanationProtocol(Protocol):
    def explain(
        self,
        ranked: list[ScoredHypothesis],
        evidence: list[EvidenceChunk],
        kg: KGProtocol,
        trace: TraceRecord | None = None,
    ) -> list[ExplainedHypothesis]:
        ...


class ExportProtocol(Protocol):
    def export(self, result: RunResult, session_id: str) -> str:
        ...
