from __future__ import annotations

import pytest

from hfabric.obs.redaction import (
    REDACTED_MARKER,
    redact_log_message,
    redact_text,
    redact_trace,
)


class TestRedactText:
    def test_short_text_preserved(self):
        text = "Short text"
        assert redact_text(text, max_length=100) == text

    def test_long_text_redacted(self):
        text = "x" * 200
        assert redact_text(text, max_length=100) == REDACTED_MARKER

    def test_empty_text(self):
        assert redact_text("") == ""
        assert redact_text(None) is None

    def test_max_length_boundary(self):
        text = "x" * 100
        assert redact_text(text, max_length=100) == text

        text2 = "x" * 101
        assert redact_text(text2, max_length=100) == REDACTED_MARKER

    def test_redacts_source_patterns_in_short_text(self):
        text = "See report-12345 for details"
        out = redact_text(text, max_length=100)
        assert "report-12345" not in out
        assert REDACTED_MARKER in out

    def test_redacts_multiple_source_patterns(self):
        text = "patent-abc and doc-99 referenced"
        out = redact_text(text, max_length=200)
        assert "patent-abc" not in out
        assert "doc-99" not in out

    def test_preserves_normal_short_text(self):
        text = "Xanthate improves gold recovery"
        assert redact_text(text) == text


class TestRedactTrace:
    def test_redacts_text_fields(self):
        record = {
            "text": "very long text " * 50,
            "content": "long content " * 50,
            "run_id": "run_123",
            "chunk_id": "chunk_001",
        }
        result = redact_trace(record)
        assert result["text"] == REDACTED_MARKER
        assert result["content"] == REDACTED_MARKER
        assert result["run_id"] == "run_123"
        assert result["chunk_id"] == "chunk_001"

    def test_preserves_ids(self):
        record = {"claim": "long claim text " * 50, "chunk_id": "c1", "evidence_refs": ["c1", "c2"]}
        result = redact_trace(record)
        assert result["chunk_id"] == "c1"
        assert result["evidence_refs"] == ["c1", "c2"]

    def test_redacts_object(self):
        class FakeRecord:
            text = "content " * 60
            run_id = "run_1"

        record = FakeRecord()
        redact_trace(record)
        assert record.text == REDACTED_MARKER
        assert record.run_id == "run_1"


class TestRedactLogMessage:
    def test_redacts_source_identifiers(self):
        msg = "Error processing report-12345"
        assert REDACTED_MARKER in redact_log_message(msg)

    def test_preserves_normal_logs(self):
        msg = "Stage completed successfully"
        assert redact_log_message(msg) == msg
