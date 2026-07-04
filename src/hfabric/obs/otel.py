from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from hfabric.obs.traces import TraceCollector


@dataclass
class OTelSpan:
    name: str
    run_id: str
    stage: str
    attributes: dict[str, Any] = field(default_factory=dict)
    _start_time: float = 0.0
    _parent: OTelSpan | None = None
    _children: list[OTelSpan] = field(default_factory=list)

    def __enter__(self):
        self._start_time = time.time()
        return self

    def __exit__(self, *args):
        self.attributes["latency_ms"] = (time.time() - self._start_time) * 1000

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def set_status(self, status: str, description: str = "") -> None:
        self.attributes["status"] = status
        if description:
            self.attributes["status_description"] = description


class OTelTracer:
    def __init__(self, trace_collector: TraceCollector) -> None:
        self._collector = trace_collector
        self._current_spans: list[OTelSpan] = []

    def start_span(
        self,
        name: str,
        run_id: str,
        stage: str = "",
        parent: OTelSpan | None = None,
    ) -> OTelSpan:
        span = OTelSpan(name=name, run_id=run_id, stage=stage or name)
        span.set_attribute("run_id", run_id)
        span.set_attribute("stage", stage or name)
        span._parent = parent
        if parent is not None:
            parent._children.append(span)
        return span

    def end_span(
        self,
        span: OTelSpan,
        token_in: int = 0,
        token_out: int = 0,
        slot: str = "",
    ) -> None:
        latency_ms = (time.time() - span._start_time) * 1000
        span.attributes["latency_ms"] = latency_ms

        self._collector.record(
            run_id=span.run_id,
            stage=span.attributes.get("stage", span.stage),
            slot=slot or span.name,
            token_in=token_in,
            token_out=token_out,
            latency_ms=latency_ms,
            status=span.attributes.get("status", "ok"),
        )

    def start_stage_span(self, run_id: str, stage: str) -> OTelSpan:
        return self.start_span(stage, run_id, stage)
