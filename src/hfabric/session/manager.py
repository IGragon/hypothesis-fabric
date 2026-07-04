from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone


class SessionManager:
    def __init__(self, base_dir: str = "sessions") -> None:
        self._base_dir = base_dir

    def create_session(self, nl_query: str, constraints: str = "") -> dict:
        session_id = str(uuid.uuid4())[:8]
        session_dir = os.path.join(self._base_dir, session_id)

        os.makedirs(os.path.join(session_dir, "raw_files"), exist_ok=True)
        os.makedirs(os.path.join(session_dir, "index"), exist_ok=True)
        os.makedirs(os.path.join(session_dir, "export"), exist_ok=True)

        meta = {
            "session_id": session_id,
            "nl_query": nl_query,
            "constraints": constraints,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "created",
        }
        meta_path = os.path.join(session_dir, "meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

        return meta

    def get_session(self, session_id: str) -> dict | None:
        meta_path = os.path.join(self._base_dir, session_id, "meta.json")
        if not os.path.isfile(meta_path):
            return None
        with open(meta_path, encoding="utf-8") as f:
            return json.load(f)

    def session_dir(self, session_id: str) -> str:
        return os.path.join(self._base_dir, session_id)

    def raw_files_dir(self, session_id: str) -> str:
        return os.path.join(self._base_dir, session_id, "raw_files")

    def index_dir(self, session_id: str) -> str:
        return os.path.join(self._base_dir, session_id, "index")

    def export_dir(self, session_id: str) -> str:
        return os.path.join(self._base_dir, session_id, "export")

    _SUPPORTED = (".pdf", ".xlsx", ".docx", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp")

    def has_raw_files(self, session_id: str) -> bool:
        raw = self.raw_files_dir(session_id)
        if not os.path.isdir(raw):
            return False
        return any(f.lower().endswith(self._SUPPORTED) for f in os.listdir(raw))

    def update_status(self, session_id: str, status: str) -> None:
        meta = self.get_session(session_id)
        if meta is None:
            return
        meta["status"] = status
        meta_path = os.path.join(self._base_dir, session_id, "meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
