from __future__ import annotations

import csv
import io
import os

from hfabric.schemas import RunResult


def write_csv(result: RunResult, session_id: str) -> str:
    export_dir = os.path.join("sessions", session_id, "export")
    os.makedirs(export_dir, exist_ok=True)
    path = os.path.join(export_dir, "hypotheses.csv")

    rows: list[dict[str, str]] = []
    for rank, eh in enumerate(result.ranked, start=1):
        h = eh.scored.hypothesis
        feats = eh.scored.features
        cited = "; ".join(
            (c.meta.get("url") or c.meta.get("title") or c.chunk_id)
            for c in eh.scored.cited_refs.values()
        )
        rows.append({
            "rank": str(rank),
            "run_id": result.run_id,
            "claim": h.claim,
            "mechanism": h.mechanism,
            "expected_effect": h.expected_effect,
            "score": f"{eh.scored.score:.4f}",
            "novelty": f"{feats.get('novelty', 0.0):.4f}",
            "feasibility": f"{feats.get('feasibility', 0.0):.4f}",
            "effect": f"{feats.get('effect', 0.0):.4f}",
            "risk": f"{feats.get('risk', 0.0):.4f}",
            "realizability": f"{feats.get('realizability', 0.0):.4f}",
            "justification": eh.justification,
            "best_practices": eh.best_practices,
            "actionable_now": eh.actionable_now,
            "uncertainty": eh.uncertainty,
            "verification_plan": eh.verification_plan,
            "cited_refs": cited,
            "external_urls": "; ".join(eh.external_urls),
        })

    fieldnames = [
        "rank", "run_id", "claim", "mechanism", "expected_effect", "score",
        "novelty", "feasibility", "effect", "risk", "realizability",
        "justification", "best_practices", "actionable_now", "uncertainty",
        "verification_plan", "cited_refs", "external_urls",
    ]

    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fieldnames)
    writer.writeheader()
    for r in rows:
        writer.writerow(r)

    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(out.getvalue())

    return path