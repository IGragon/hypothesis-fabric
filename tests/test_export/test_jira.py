from __future__ import annotations

import pytest

from hfabric.export.jira import JiraExporter


class TestJiraExporter:
    def test_create_task_returns_key(self):
        exporter = JiraExporter(
            base_url="https://jira.example.com",
            api_token="token",
            project_key="HF",
        )
        result = exporter.create_task(
            summary="Test hypothesis task",
            description="Description of the task",
        )
        assert result is not None
        assert "key" in result
        assert result["key"].startswith("HF-")

    def test_external_id_idempotency(self):
        exporter = JiraExporter(
            base_url="https://jira.example.com",
            api_token="token",
            project_key="TEST",
        )
        result = exporter.check_existing("ext-123")
        assert result is None

    def test_create_task_with_labels(self):
        exporter = JiraExporter("https://jira.example.com", "token", "HF")
        result = exporter.create_task("Test", "Desc", labels=["metallurgy", "flotation"])
        assert result is not None

    def test_create_task_empty_labels(self):
        exporter = JiraExporter("https://jira.example.com", "token", "HF")
        result = exporter.create_task("Test", "Desc")
        assert result is not None
        assert isinstance(result, dict)
