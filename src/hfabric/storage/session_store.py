from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from hfabric.schemas import TraceRecord

STAGES = [
    "kpi_parse",
    "retrieve",
    "generate",
    "cite_bind",
    "score",
    "constraint_check",
    "explain",
    "export",
]


class SessionStore:
    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA busy_timeout=30000;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._create_tables()

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS stage_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                started_at TEXT,
                ended_at TEXT,
                error TEXT
            );

            CREATE TABLE IF NOT EXISTS artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                name TEXT NOT NULL,
                value_json TEXT NOT NULL,
                UNIQUE(run_id, stage, name)
            );

            CREATE TABLE IF NOT EXISTS traces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                slot TEXT,
                token_in INTEGER DEFAULT 0,
                token_out INTEGER DEFAULT 0,
                latency_ms REAL DEFAULT 0,
                status TEXT DEFAULT 'ok'
            );

            CREATE TABLE IF NOT EXISTS evals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                metric TEXT NOT NULL,
                value REAL NOT NULL
            );
        """)
        self._conn.commit()

    def init(self, run_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "DELETE FROM stage_state WHERE run_id = ?", (run_id,)
        )
        self._conn.executemany(
            "INSERT INTO stage_state (run_id, stage, status, started_at) VALUES (?, ?, 'pending', ?)",
            [(run_id, stage, now) for stage in STAGES],
        )
        self._conn.commit()

    def save_artifact(self, run_id: str, stage: str, name: str, value_json: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO artifacts (run_id, stage, name, value_json) VALUES (?, ?, ?, ?)",
            (run_id, stage, name, value_json),
        )
        self._conn.commit()

    def load_artifact(self, run_id: str, stage: str, name: str) -> str | None:
        row = self._conn.execute(
            "SELECT value_json FROM artifacts WHERE run_id = ? AND stage = ? AND name = ?",
            (run_id, stage, name),
        ).fetchone()
        return row[0] if row else None

    def save_trace(self, trace: TraceRecord) -> None:
        self._conn.execute(
            "INSERT INTO traces (run_id, stage, slot, token_in, token_out, latency_ms, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                trace.run_id,
                trace.stage,
                trace.slot,
                trace.token_in,
                trace.token_out,
                trace.latency_ms,
                trace.status,
            ),
        )
        self._conn.commit()

    def save_eval(self, run_id: str, metric: str, value: float) -> None:
        self._conn.execute(
            "INSERT INTO evals (run_id, metric, value) VALUES (?, ?, ?)",
            (run_id, metric, value),
        )
        self._conn.commit()

    def set_stage_state(self, run_id: str, stage: str, status: str, error: str | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        if status == "running":
            self._conn.execute(
                "UPDATE stage_state SET status = ?, started_at = ?, error = ? WHERE run_id = ? AND stage = ?",
                (status, now, error, run_id, stage),
            )
        elif status in ("done", "error", "incomplete"):
            self._conn.execute(
                "UPDATE stage_state SET status = ?, ended_at = ?, error = ? WHERE run_id = ? AND stage = ?",
                (status, now, error, run_id, stage),
            )
        else:
            self._conn.execute(
                "UPDATE stage_state SET status = ?, error = ? WHERE run_id = ? AND stage = ?",
                (status, error, run_id, stage),
            )
        self._conn.commit()

    def get_stage_state(self, run_id: str, stage: str) -> dict | None:
        row = self._conn.execute(
            "SELECT id, run_id, stage, status, started_at, ended_at, error FROM stage_state WHERE run_id = ? AND stage = ?",
            (run_id, stage),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "run_id": row[1],
            "stage": row[2],
            "status": row[3],
            "started_at": row[4],
            "ended_at": row[5],
            "error": row[6],
        }

    def get_all_stages(self, run_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, run_id, stage, status, started_at, ended_at, error FROM stage_state WHERE run_id = ? ORDER BY id",
            (run_id,),
        ).fetchall()
        return [
            {
                "id": r[0],
                "run_id": r[1],
                "stage": r[2],
                "status": r[3],
                "started_at": r[4],
                "ended_at": r[5],
                "error": r[6],
            }
            for r in rows
        ]

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass
