from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from hfabric.obs.traces import TraceCollector
from hfabric.schemas import TraceRecord


class TestTraceCollectorRecord:
    def test_creates_and_persists_trace_record(self) -> None:
        store = MagicMock()
        tc = TraceCollector(store)

        result = tc.record(
            run_id="run-1",
            stage="generate",
            slot="slot-a",
            token_in=100,
            token_out=50,
            latency_ms=250.0,
            status="ok",
        )

        store.save_trace.assert_called_once()
        saved = store.save_trace.call_args[0][0]
        assert isinstance(saved, TraceRecord)
        assert saved.run_id == "run-1"
        assert saved.stage == "generate"
        assert saved.slot == "slot-a"
        assert saved.token_in == 100
        assert saved.token_out == 50
        assert saved.latency_ms == 250.0
        assert saved.status == "ok"
        assert result == saved

    def test_record_defaults(self) -> None:
        store = MagicMock()
        tc = TraceCollector(store)

        result = tc.record(run_id="r", stage="s")

        store.save_trace.assert_called_once()
        saved = store.save_trace.call_args[0][0]
        assert saved.slot is None
        assert saved.token_in == 0
        assert saved.token_out == 0
        assert saved.latency_ms == 0.0
        assert saved.status == "ok"


class TestTraceCollectorWrapLLMCall:
    def test_extracts_token_counts_from_response_metadata(self) -> None:
        store = MagicMock()
        tc = TraceCollector(store)

        response = MagicMock()
        response.response_metadata = {
            "token_usage": {
                "prompt_tokens": 200,
                "completion_tokens": 80,
            }
        }

        def llm_fn(*args: object, **kwargs: object) -> MagicMock:
            return response

        result = tc.wrap_llm_call("run-1", "generate", "slot-1", llm_fn)

        assert result == response
        store.save_trace.assert_called_once()
        trace = store.save_trace.call_args[0][0]
        assert trace.token_in == 200
        assert trace.token_out == 80
        assert trace.status == "ok"
        assert trace.latency_ms >= 0

    def test_extracts_token_counts_from_usage_metadata(self) -> None:
        store = MagicMock()
        tc = TraceCollector(store)

        response = MagicMock()
        response.response_metadata = {}
        response.usage_metadata = {
            "input_tokens": 150,
            "output_tokens": 60,
        }

        def llm_fn(*args: object, **kwargs: object) -> MagicMock:
            return response

        result = tc.wrap_llm_call("run-2", "score", "slot-b", llm_fn)

        assert result == response
        trace = store.save_trace.call_args[0][0]
        assert trace.token_in == 150
        assert trace.token_out == 60

    def test_defaults_to_zero_tokens_on_extraction_failure(self) -> None:
        store = MagicMock()
        tc = TraceCollector(store)

        response = MagicMock(spec=[])
        del response.response_metadata
        del response.usage_metadata

        def llm_fn(*args: object, **kwargs: object) -> MagicMock:
            return response

        result = tc.wrap_llm_call("run-3", "stage-x", "slot-y", llm_fn)

        assert result == response
        trace = store.save_trace.call_args[0][0]
        assert trace.token_in == 0
        assert trace.token_out == 0

    def test_records_error_on_exception(self) -> None:
        store = MagicMock()
        tc = TraceCollector(store)

        def llm_fn(*args: object, **kwargs: object) -> object:
            raise ValueError("bang")

        with pytest.raises(ValueError, match="bang"):
            tc.wrap_llm_call("run-4", "stage-e", "slot-e", llm_fn)

        store.save_trace.assert_called_once()
        trace = store.save_trace.call_args[0][0]
        assert trace.status == "error"
        assert trace.token_in == 0
        assert trace.token_out == 0

    def test_passes_args_and_kwargs_to_llm_fn(self) -> None:
        store = MagicMock()
        tc = TraceCollector(store)

        response = MagicMock()
        response.response_metadata = {}
        response.usage_metadata = {}

        def llm_fn(a: object, b: object, *, key: object = None) -> MagicMock:
            assert a == "arg1"
            assert b == "arg2"
            assert key == "val"
            return response

        tc.wrap_llm_call("r", "s", "sl", llm_fn, "arg1", "arg2", key="val")
