from __future__ import annotations

import json
import os
import re

from hfabric.schemas import RunResult


def _api_base() -> str:
    return os.environ.get("HFABRIC_API_BASE", "http://localhost:8000").rstrip("/")


def _file_url(session_id: str, path: str, api_base: str | None = None) -> str:
    """Build a downloadable HTTP URL for a session raw file."""
    base = (api_base or _api_base()).rstrip("/")
    filename = os.path.basename(path)
    return f"{base}/sessions/{session_id}/files/{filename}"


def _linkify(text: str, cited_refs: dict, session_id: str = "", api_base: str | None = None) -> str:
    if not text:
        return text

    base = api_base or _api_base()

    def repl(m: "re.Match") -> str:
        marker = m.group(1).strip()
        chunk = cited_refs.get(marker)
        url = None
        if chunk is not None:
            url = chunk.meta.get("url")
        else:
            for c in cited_refs.values():
                if c.meta.get("url") == marker:
                    url = marker
                    break
        if url:
            return f"[{marker}]({url})"
        if chunk is not None:
            path = chunk.meta.get("path", "")
            if path and session_id:
                return f"[{marker}]({_file_url(session_id, path, base)})"
        return f"[{marker}]"

    return re.sub(r"\[([^\]\n]+)\]", repl, text)


def write_export(result: RunResult, session_id: str) -> tuple[str, str]:
    export_dir = os.path.join("sessions", session_id, "export")
    os.makedirs(export_dir, exist_ok=True)

    json_path = os.path.join(export_dir, "hypotheses.json")
    md_path = os.path.join(export_dir, "report.md")

    json_data = result.model_dump_json(indent=2, exclude_none=True)
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(json_data)

    md_content = _build_report_md(result, session_id)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    return json_path, md_path


def _build_report_md(result: RunResult, session_id: str = "") -> str:
    lines: list[str] = []

    lines.append("# Hypothesis Fabric — Research Report")
    lines.append("")
    lines.append(f"**Query:** {result.query}")
    lines.append(f"**Run ID:** {result.run_id}")
    lines.append(f"**Status:** {result.status}")
    for note in result.notes:
        lines.append(f"**Note:** {note}")
    lines.append("")

    kpi = result.kpi.kpi
    lines.append("## KPI Summary")
    lines.append("")
    lines.append("| Metric | Direction | Target |")
    lines.append("|--------|-----------|--------|")
    target_str = kpi.target if kpi.target else "N/A"
    lines.append(f"| {kpi.metric} | {kpi.direction} | {target_str} |")
    lines.append("")

    constraints = result.kpi.constraints
    if constraints:
        lines.append("**Constraints:**")
        lines.append("")
        for c in constraints:
            lines.append(f"- {c}")
    else:
        lines.append("**Constraints:** None")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Ranked Hypotheses")
    lines.append("")

    for rank, eh in enumerate(result.ranked, start=1):
        h = eh.scored.hypothesis
        score = eh.scored.score
        features = eh.scored.features

        lines.append(f"### #{rank}. {h.claim} (Score: {score:.2f})")
        lines.append("")

        violations = features.get("violation_count", 0)
        if eh.constraint_violations:
            lines.append(f"**⚠ Нарушения ограничений:** {len(eh.constraint_violations)}")
            lines.append("")
            for v in eh.constraint_violations:
                lines.append(f"- {v}")
            lines.append("")
        elif violations > 0:
            lines.append(f"**⚠ Нарушения ограничений:** {int(violations)} (штраф применён к оценке)")
            lines.append("")

        lines.append(f"**Mechanism:** {h.mechanism}")
        lines.append(f"**Expected Effect:** {h.expected_effect}")
        lines.append("")

        lines.append("| Feature | Value |")
        lines.append("|---------|-------|")
        for fname, fval in features.items():
            if isinstance(fval, float):
                lines.append(f"| {fname} | {fval:.2f} |")
            else:
                lines.append(f"| {fname} | {fval} |")
        lines.append("")

        cited_refs = eh.scored.cited_refs

        def lk(text: str) -> str:
            return _linkify(text, cited_refs, session_id)

        lines.append(f"**Justification:** {lk(eh.justification)}")
        lines.append("")
        lines.append(f"**Novelty:** {lk(eh.novelty)}")
        lines.append(f"**Risks:** {lk(eh.risks)}")
        lines.append(f"**Why it matters (value / KPI):** {lk(eh.why_it_matters)}")
        lines.append("")

        if eh.effect_cause_examples:
            lines.append("**Effect–cause examples:**")
            lines.append("")
            for ex in eh.effect_cause_examples:
                lines.append(f"- {lk(ex)}")
            lines.append("")

        lines.append(f"**General approach:** {lk(eh.general_approach)}")
        lines.append("")
        lines.append(f"**What to do now:** {lk(eh.actionable_now)}")
        lines.append("")
        lines.append(f"**Existing best practices:** {lk(eh.best_practices)}")
        lines.append("")
        lines.append(f"**Uncertainty:** {lk(eh.uncertainty)}")
        lines.append(f"**Verification plan (roadmap):** {lk(eh.verification_plan)}")
        lines.append("")

        if cited_refs:
            lines.append("**Evidence / Sources:**")
            lines.append("")
            for cid, chunk in cited_refs.items():
                url = chunk.meta.get("url")
                if url:
                    title = chunk.meta.get("title") or url
                    lines.append(f"- `[{cid}]` [{title}]({url})")
                else:
                    doc = chunk.meta.get("doc_id", chunk.doc_id or cid)
                    path = chunk.meta.get("path", "")
                    if path and session_id:
                        link = _file_url(session_id, path)
                        lines.append(f"- `[{cid}]` [{doc}]({link}) — {chunk.text[:280]}")
                    else:
                        src = f" — _{doc}_" if doc else ""
                        lines.append(f"- `[{cid}]`{src}: {chunk.text[:280]}")
            lines.append("")
        else:
            lines.append("**Evidence / Sources:** None")
            lines.append("")

        if eh.external_urls:
            lines.append(f"**External sources cited:** {len(eh.external_urls)}")
            lines.append("")

        neighbourhood = eh.graph_neighbourhood
        if neighbourhood:
            lines.append("**Knowledge Graph Neighbourhood:**")
            lines.append("```")
            for node in neighbourhood:
                lines.append(node)
            lines.append("```")
        else:
            lines.append("**Knowledge Graph Neighbourhood:** None")
            lines.append("```")
            lines.append("```")
        lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)
