from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone


class FeedbackStore:
    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._create_tables()
        self._migrate_features_column()

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS feedback_labels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                hypothesis_claim TEXT NOT NULL,
                label TEXT NOT NULL CHECK(label IN ('accepted', 'rejected', 'adjusted')),
                expert_id TEXT NOT NULL,
                comment TEXT DEFAULT '',
                features TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );
        """)
        self._conn.commit()

    def _migrate_features_column(self) -> None:
        cols = {
            r[1]
            for r in self._conn.execute("PRAGMA table_info(feedback_labels)").fetchall()
        }
        if "features" not in cols:
            self._conn.execute(
                "ALTER TABLE feedback_labels ADD COLUMN features TEXT DEFAULT ''"
            )
            self._conn.commit()

    def save_label(
        self,
        run_id: str,
        hypothesis_claim: str,
        label: str,
        expert_id: str,
        comment: str = "",
        features: dict | None = None,
    ) -> int:
        created_at = datetime.now(timezone.utc).isoformat()
        features_json = json.dumps(features) if features else ""
        cursor = self._conn.execute(
            "INSERT INTO feedback_labels "
            "(run_id, hypothesis_claim, label, expert_id, comment, features, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (run_id, hypothesis_claim, label, expert_id, comment, features_json, created_at),
        )
        self._conn.commit()
        return cursor.lastrowid

    def _row_to_dict(self, r: tuple) -> dict:
        features: dict = {}
        if r[6]:
            try:
                features = json.loads(r[6])
            except (json.JSONDecodeError, TypeError):
                features = {}
        return {
            "id": r[0],
            "run_id": r[1],
            "hypothesis_claim": r[2],
            "label": r[3],
            "expert_id": r[4],
            "comment": r[5],
            "features": features,
            "created_at": r[7],
        }

    def get_labels(self, hypothesis_claim: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, run_id, hypothesis_claim, label, expert_id, comment, features, created_at "
            "FROM feedback_labels WHERE hypothesis_claim = ? ORDER BY created_at",
            (hypothesis_claim,),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_all_labels(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, run_id, hypothesis_claim, label, expert_id, comment, features, created_at "
            "FROM feedback_labels ORDER BY created_at",
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def delete_label(self, label_id: int) -> None:
        self._conn.execute("DELETE FROM feedback_labels WHERE id = ?", (label_id,))
        self._conn.commit()

    def get_label_conflicts(self) -> list[dict]:
        rows = self._conn.execute("""
            SELECT hypothesis_claim, COUNT(DISTINCT label) as label_count
            FROM feedback_labels
            GROUP BY hypothesis_claim
            HAVING label_count > 1
        """).fetchall()
        return [
            {"hypothesis_claim": r[0], "label_count": r[1]}
            for r in rows
        ]
