from __future__ import annotations

from typing import Any

from hfabric.config import MVPConfig
from hfabric.schemas import EvidenceChunk, Hypothesis, KPIParsed, TraceRecord

from .synth import CandidateSynthesizer


def generate(
    evidence: list[EvidenceChunk],
    kpi: KPIParsed,
    trace: TraceRecord | None = None,
    config: MVPConfig | None = None,
    llm: Any = None,
) -> list[Hypothesis]:
    cfg = config or MVPConfig()
    if llm is None:
        from hfabric.llm import create_chat_model
        llm = create_chat_model(cfg.provider, cfg.model)
    synth = CandidateSynthesizer(llm, cfg)
    return synth.generate(evidence, kpi, trace)


__all__ = ["CandidateSynthesizer", "generate"]
