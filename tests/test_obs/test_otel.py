from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from hfabric.obs.otel import OTelSpan, OTelTracer
from hfabric.obs.traces import TraceCollector
from hfabric.storage.session_store import SessionStore


@pytest.fixture
def store():
    store = MagicMock(spec=SessionStore)
    return store


@pytest.fixture
def tracer(store):
    collector = TraceCollector(store)
    return OTelTracer(collector)


class TestOTelSpan:
    def test_span_context_manager(self):
        with OTelSpan(name="test", run_id="r1", stage="s1") as span:
            span.set_attribute("key", "value")
            time.sleep(0.01)
        assert span.attributes["latency_ms"] > 0
        assert span.attributes["key"] == "value"

    def test_span_attributes(self):
        span = OTelSpan(name="test", run_id="r1", stage="s1")
        span.set_attribute("token_in", 100)
        span.set_status("ok")
        assert span.attributes["token_in"] == 100
        assert span.attributes["status"] == "ok"


class TestOTelTracer:
    def test_start_and_end_span(self, tracer, store):
        span = tracer.start_stage_span("run_1", "retrieve")
        span.set_attribute("token_in", 200)
        tracer.end_span(span, token_in=200, token_out=100)

        assert store.save_trace.called

    def test_span_parent_child(self, tracer):
        parent = tracer.start_stage_span("run_1", "generate")
        child = tracer.start_span("llm_call", "run_1", "generate", parent=parent)
        assert child._parent is parent
        assert len(parent._children) == 1

    def test_end_span_records_trace(self, tracer, store):
        span = tracer.start_stage_span("run_1", "explain")
        tracer.end_span(span, token_in=50, token_out=200, slot="explain_slot")
        assert store.save_trace.called

        call_args = store.save_trace.call_args[0][0]
        assert call_args.run_id == "run_1"
        assert call_args.stage == "explain"
        assert call_args.slot == "explain_slot"

    def test_multiple_stages(self, tracer, store):
        for stage in ["kpi_parse", "retrieve", "generate"]:
            span = tracer.start_stage_span("run_1", stage)
            tracer.end_span(span, token_in=10, token_out=5)

        assert store.save_trace.call_count == 3
