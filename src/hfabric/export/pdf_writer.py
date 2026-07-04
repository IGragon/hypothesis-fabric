from __future__ import annotations

import os
import re

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from reportlab.lib import colors

from hfabric.schemas import RunResult


def _linkify_pdf(text: str, cited_refs: dict) -> str:
    if not text:
        return text

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
            return f'<a href="{url}">[{marker}]</a>'
        return f"[{marker}]"

    return re.sub(r"\[([^\]\n]+)\]", repl, text)


def write_pdf(result: RunResult, session_id: str) -> str:
    from reportlab.lib.pagesizes import A4

    export_dir = os.path.join("sessions", session_id, "export")
    os.makedirs(export_dir, exist_ok=True)
    path = os.path.join(export_dir, "report.pdf")

    doc = SimpleDocTemplate(
        path,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="Hypothesis Fabric Report",
    )
    base = getSampleStyleSheet()
    h1 = base["Heading1"]
    h2 = base["Heading2"]
    h3 = ParagraphStyle("H3", parent=base["Heading2"], fontSize=11, spaceBefore=6, spaceAfter=3)
    body = ParagraphStyle("Body", parent=base["BodyText"], fontSize=9, leading=12, spaceAfter=4)
    small = ParagraphStyle("Small", parent=body, fontSize=8, textColor=colors.grey)

    story = []
    story.append(Paragraph("Hypothesis Fabric — Research Report", h1))
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"<b>Query:</b> {result.query}", body))
    story.append(Paragraph(f"<b>Run ID:</b> {result.run_id}", body))
    story.append(Paragraph(f"<b>Status:</b> {result.status}", body))
    for note in result.notes:
        story.append(Paragraph(f"<b>Note:</b> {note}", body))
    story.append(Spacer(1, 8))

    kpi = result.kpi.kpi
    story.append(Paragraph("KPI Summary", h2))
    story.append(_table(
        ["Metric", "Direction", "Target"],
        [[kpi.metric, kpi.direction, kpi.target or "N/A"]],
    ))
    story.append(Spacer(1, 4))
    if result.kpi.constraints:
        story.append(Paragraph("<b>Constraints:</b><br/>" + "<br/>".join(
            f"- {c}" for c in result.kpi.constraints), body))
    else:
        story.append(Paragraph("<b>Constraints:</b> None", body))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Ranked Hypotheses", h2))

    for rank, eh in enumerate(result.ranked, start=1):
        h = eh.scored.hypothesis
        score = eh.scored.score
        features = eh.scored.features
        cited_refs = eh.scored.cited_refs

        def lk(text: str) -> str:
            return _linkify_pdf(text, cited_refs)

        story.append(Paragraph(f"#{rank}. {h.claim} (Score: {score:.2f})", h3))
        story.append(Paragraph(f"<b>Mechanism:</b> {h.mechanism}", body))
        story.append(Paragraph(f"<b>Expected Effect:</b> {h.expected_effect}", body))
        story.append(_table(
            ["Feature", "Value"],
            [[k, f"{v:.2f}"] for k, v in features.items()],
        ))
        story.append(Paragraph(f"<b>Justification:</b> {lk(eh.justification)}", body))
        story.append(Paragraph(f"<b>Novelty:</b> {lk(eh.novelty)}", body))
        story.append(Paragraph(f"<b>Risks:</b> {lk(eh.risks)}", body))
        story.append(Paragraph(f"<b>Why it matters:</b> {lk(eh.why_it_matters)}", body))
        if eh.effect_cause_examples:
            story.append(Paragraph("<b>Effect–cause examples:</b><br/>" + "<br/>".join(
                f"- {lk(ex)}" for ex in eh.effect_cause_examples), body))
        story.append(Paragraph(f"<b>General approach:</b> {lk(eh.general_approach)}", body))
        story.append(Paragraph(f"<b>What to do now:</b> {lk(eh.actionable_now)}", body))
        story.append(Paragraph(f"<b>Best practices:</b> {lk(eh.best_practices)}", body))
        story.append(Paragraph(f"<b>Uncertainty:</b> {lk(eh.uncertainty)}", body))
        story.append(Paragraph(f"<b>Verification plan (roadmap):</b> {lk(eh.verification_plan)}", body))

        if cited_refs:
            story.append(Paragraph("<b>Evidence / Sources:</b><br/>" + "<br/>".join(
                f"- [{cid}] {c.meta.get('url') or c.meta.get('title') or (c.text[:200])}"
                for cid, c in cited_refs.items()), small))
        else:
            story.append(Paragraph("<b>Evidence / Sources:</b> None", body))

        if eh.external_urls:
            story.append(Paragraph(f"<i>External sources cited: {len(eh.external_urls)}</i>", small))

        if eh.graph_neighbourhood:
            story.append(Paragraph("<b>Knowledge Graph Neighbourhood:</b><br/>" + "<br/>".join(
                f"- {n}" for n in eh.graph_neighbourhood), small))
        story.append(Spacer(1, 10))

    doc.build(story)
    return path


def _table(headers: list[str], rows: list[list[str]]):
    data = [headers] + rows
    t = Table(data, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t