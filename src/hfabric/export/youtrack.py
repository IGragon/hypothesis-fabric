from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass
class YouTrackExporter:
    base_url: str
    token: str
    project_id: str

    def _is_configured(self) -> bool:
        return bool(
            self.base_url and self.token and self.project_id
            and os.environ.get("YOUTRACK_BASE_URL")
        )

    def create_task(
        self,
        summary: str,
        description: str,
        external_id: str = "",
    ) -> dict[str, Any] | None:
        if external_id and self.check_existing(external_id):
            return None
        if not self._is_configured():
            return {
                "status": "mocked",
                "id": "YT-123",
                "idReadable": f"{self.project_id}-123",
                "summary": summary,
                "external_id": external_id,
            }
        try:
            import httpx

            payload: dict[str, Any] = {
                "project": {"id": self.project_id},
                "summary": summary,
                "description": description,
            }
            if external_id:
                payload["customFields"] = [
                    {
                        "$type": "SingleEnumIssueCustomField",
                        "name": "External ID",
                        "value": {"$type": "EnumValue", "name": external_id},
                    }
                ]
            base = self.base_url.rstrip("/")
            r = httpx.post(
                f"{base}/api/issues",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                params={"fields": "id,idReadable,summary"},
                timeout=15.0,
            )
            if r.status_code in (200, 201):
                data = r.json()
                return {
                    "status": "created",
                    "id": data.get("id", ""),
                    "idReadable": data.get("idReadable", ""),
                    "summary": summary,
                    "external_id": external_id,
                }
            return {
                "status": "error",
                "id": "",
                "idReadable": "",
                "summary": summary,
                "external_id": external_id,
                "error": f"{r.status_code}: {r.text[:200]}",
            }
        except Exception as exc:
            return {
                "status": "error",
                "id": "",
                "idReadable": "",
                "summary": summary,
                "external_id": external_id,
                "error": str(exc),
            }

    def check_existing(self, external_id: str) -> dict[str, Any] | None:
        if not external_id or not self._is_configured():
            return None
        try:
            import httpx

            base = self.base_url.rstrip("/")
            query = f'project: {self.project_id} External ID: {external_id}'
            r = httpx.get(
                f"{base}/api/issues",
                params={"query": query, "fields": "id,idReadable,summary", "$top": "1"},
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/json",
                },
                timeout=15.0,
            )
            if r.status_code == 200:
                issues = r.json()
                if issues:
                    return issues[0]
            return None
        except Exception:
            return None