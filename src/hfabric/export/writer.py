from __future__ import annotations

import json
import os

from hfabric.schemas import RunResult


def write_export(result: RunResult, session_id: str) -> tuple[str, str]:
    export_dir = os.path.join("sessions", session_id, "export")
    os.makedirs(export_dir, exist_ok=True)

    json_path = os.path.join(export_dir, "hypotheses.json")
    md_path = os.path.join(export_dir, "report.md")

    json_data = result.model_dump_json(indent=2, exclude_none=True)
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(json_data)

    md_content = _build_report_md(result)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    return json_path, md_path


def _build_report_md(result: RunResult) -> str:
    lines: list[str] = []

    lines.append("# Hypothesis Fabric — Research Report")
    lines.append("")
    lines.append(f"**Query:** {result.query}")
    lines.append(f"**Run ID:** {result.run_id}")
    lines.append(f"**Status:** {result.status}")
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
        lines.append(f"**Mechanism:** {h.mechanism}")
        lines.append(f"**Expected Effect:** {h.expected_effect}")
        lines.append("")

        lines.append("| Feature | Value |")
        lines.append("|---------|-------|")
        for fname, fval in features.items():
            lines.append(f"| {fname} | {fval:.2f} |")
        lines.append("")

        cited_refs = eh.scored.cited_refs
        if cited_refs:
            lines.append("**Evidence:**")
            lines.append("")
            for chunk in cited_refs.values():
                lines.append(f"> {chunk.text}")
                lines.append("")
        else:
            lines.append("**Evidence:** None")
            lines.append("")

        lines.append(f"**Justification:** {eh.justification}")
        lines.append(f"**Uncertainty:** {eh.uncertainty}")
        lines.append(f"**Verification Plan:** {eh.verification_plan}")
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
