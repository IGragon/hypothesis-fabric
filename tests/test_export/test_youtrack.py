from __future__ import annotations

from hfabric.export.youtrack import YouTrackExporter


class TestYouTrackExporter:
    def test_create_task_returns_mocked_when_unconfigured(self):
        exporter = YouTrackExporter(
            base_url="https://youtrack.example.com",
            token="",
            project_id="0-1",
        )
        result = exporter.create_task(summary="Test hypothesis", description="desc")
        assert result is not None
        assert result["status"] == "mocked"
        assert result["idReadable"].startswith("0-1")

    def test_create_task_mocked_includes_summary_and_external_id(self):
        exporter = YouTrackExporter("https://youtrack.example.com", "", "TEST")
        result = exporter.create_task("Test", "desc", external_id="r1:12345")
        assert result["summary"] == "Test"
        assert result["external_id"] == "r1:12345"

    def test_check_existing_returns_none_when_unconfigured(self):
        exporter = YouTrackExporter("", "", "0-0")
        assert exporter.check_existing("ext-123") is None

    def test_check_existing_returns_none_when_empty_id(self):
        exporter = YouTrackExporter("https://youtrack.example.com", "tok", "0-1")
        assert exporter.check_existing("") is None

    def test_is_configured_requires_all_three_and_env(self, monkeypatch):
        exporter = YouTrackExporter("base", "tok", "0-1")
        monkeypatch.delenv("YOUTRACK_BASE_URL", raising=False)
        assert exporter._is_configured() is False
        monkeypatch.setenv("YOUTRACK_BASE_URL", "https://youtrack.example.com")
        assert exporter._is_configured() is True

    def test_idempotency_no_external_id(self):
        exporter = YouTrackExporter("https://youtrack.example.com", "", "0-1")
        result = exporter.create_task("Test", "desc")
        assert result is not None
        assert result["status"] == "mocked"