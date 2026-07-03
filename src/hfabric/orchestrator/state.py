from __future__ import annotations

from typing import TypedDict


class RunState(TypedDict, total=False):
    run_id: str
    session_id: str
    nl_query: str
    kpi_parsed: dict | None
    evidence: list[dict]
    low_confidence: bool
    candidates: list[dict]
    cited: list[dict]
    coverage: float
    ranked: list[dict]
    explained: list[dict]
    export_path: str
    export_json_path: str
    export_md_path: str
    status: str
    errors: list[str]
    fe1_attempt: int
    fe2_attempt: int
    fe6_attempt: int
    fe4_dropped: list[str]
