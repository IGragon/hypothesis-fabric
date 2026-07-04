from __future__ import annotations

import time
from typing import Any, Callable, Protocol

from hfabric.obs.redaction import redact_trace as _redact_trace
from hfabric.schemas import TraceRecord


class _TraceStore(Protocol):
    def save_trace(self, trace: TraceRecord) -> None: ...


class TraceCollector:
    def __init__(self, store: _TraceStore) -> None:
        self._store = store

    def record(
        self,
        run_id: str,
        stage: str,
        slot: str | None = None,
        token_in: int = 0,
        token_out: int = 0,
        latency_ms: float = 0.0,
        status: str = "ok",
    ) -> TraceRecord:
        trace = TraceRecord(
            run_id=run_id,
            stage=stage,
            slot=slot,
            token_in=token_in,
            token_out=token_out,
            latency_ms=latency_ms,
            status=status,
        )
        _redact_trace(trace)
        self._store.save_trace(trace)
        return trace

    def wrap_llm_call(
        self,
        run_id: str,
        stage: str,
        slot: str,
        llm_fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        t0 = time.perf_counter()
        try:
            response = llm_fn(*args, **kwargs)
            status = "ok"
        except Exception:
            latency_ms = (time.perf_counter() - t0) * 1000
            trace = TraceRecord(
                run_id=run_id,
                stage=stage,
                slot=slot,
                token_in=0,
                token_out=0,
                latency_ms=latency_ms,
                status="error",
            )
            _redact_trace(trace)
            self._store.save_trace(trace)
            raise

        latency_ms = (time.perf_counter() - t0) * 1000
        token_in = 0
        token_out = 0

        try:
            if hasattr(response, "response_metadata"):
                rm = response.response_metadata
                if isinstance(rm, dict):
                    tu = rm.get("token_usage", {})
                    token_in = tu.get("prompt_tokens", 0)
                    token_out = tu.get("completion_tokens", 0)
            if hasattr(response, "usage_metadata"):
                um = response.usage_metadata
                if isinstance(um, dict):
                    token_in = um.get("input_tokens", token_in or 0)
                    token_out = um.get("output_tokens", token_out or 0)
        except Exception:
            pass

        self.record(
            run_id=run_id,
            stage=stage,
            slot=slot,
            token_in=token_in,
            token_out=token_out,
            latency_ms=latency_ms,
            status=status,
        )
        return response
