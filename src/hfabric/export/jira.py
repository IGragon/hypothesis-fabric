from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass
class JiraExporter:
    base_url: str
    api_token: str
    project_key: str
    email: str = ""

    def _auth(self) -> tuple[str, str] | None:
        if not (self.base_url and self.api_token and self.project_key):
            return None
        if not os.environ.get("JIRA_BASE_URL") and not self.base_url.startswith("http"):
            return None
        return self.email or "api", self.api_token

    def _is_configured(self) -> bool:
        return bool(
            self.base_url and self.api_token and self.project_key
            and os.environ.get("JIRA_BASE_URL")
        )

    def create_task(
        self,
        summary: str,
        description: str,
        labels: list[str] | None = None,
        external_id: str = "",
    ) -> dict[str, Any] | None:
        labels = labels or ["hypothesis-fabric"]
        if external_id and self.check_existing(external_id):
            return None
        if not self._is_configured():
            return {
                "status": "mocked",
                "key": f"{self.project_key}-123",
                "id": "1001",
                "summary": summary,
                "external_id": external_id,
            }
        try:
            import httpx

            payload: dict[str, Any] = {
                "fields": {
                    "project": {"key": self.project_key},
                    "summary": summary,
                    "description": description,
                    "issuetype": {"name": "Task"},
                    "labels": labels,
                }
            }
            if external_id:
                payload["fields"]["customfield_10000"] = external_id
            auth = (self.email or "api", self.api_token)
            r = httpx.post(
                f"{self.base_url.rstrip('/')}/rest/api/2/issue",
                json=payload,
                auth=auth,
                headers={"Accept": "application/json"},
                timeout=15.0,
            )
            if r.status_code in (200, 201):
                data = r.json()
                return {
                    "status": "created",
                    "key": data.get("key", ""),
                    "id": data.get("id", ""),
                    "summary": summary,
                    "external_id": external_id,
                }
            return {
                "status": "error",
                "key": "",
                "id": "",
                "summary": summary,
                "external_id": external_id,
                "error": f"{r.status_code}: {r.text[:200]}",
            }
        except Exception as exc:
            return {
                "status": "error",
                "key": "",
                "id": "",
                "summary": summary,
                "external_id": external_id,
                "error": str(exc),
            }

    def check_existing(self, external_id: str) -> dict[str, Any] | None:
        if not external_id or not self._is_configured():
            return None
        try:
            import httpx

            jql = f'project = {self.project_key} AND cf[10000] = "{external_id}"'
            r = httpx.get(
                f"{self.base_url.rstrip('/')}/rest/api/2/search",
                params={"jql": jql, "maxResults": 1},
                auth=(self.email or "api", self.api_token),
                headers={"Accept": "application/json"},
                timeout=15.0,
            )
            if r.status_code == 200:
                issues = r.json().get("issues", [])
                if issues:
                    return issues[0]
            return None
        except Exception:
            return None
