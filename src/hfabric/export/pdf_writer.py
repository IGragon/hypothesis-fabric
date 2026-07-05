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

_CYRILLIC_FONT_DIRS = [
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/truetype/liberation",
    "/usr/share/fonts/dejavu",
    "/usr/local/share/fonts",
    os.path.expanduser("~/.fonts"),
]


def _register_cyrillic_fonts() -> tuple[str, str, str]:
    """Register a Cyrillic-capable TTF font family with reportlab.

    Returns (regular_name, bold_name, italic_name).  Falls back to
    Helvetica (no Cyrillic) if no suitable TTF is found, so the PDF
    still builds (with black squares) rather than crashing.
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    candidates = [
        ("DejaVuSans", "DejaVuSans-Regular.ttf"),
        ("DejaVuSans", "DejaVuSans.ttf"),
        ("LiberationSans", "LiberationSans-Regular.ttf"),
    ]
    bold_candidates = [
        ("DejaVuSans-Bold", "DejaVuSans-Bold.ttf"),
        ("LiberationSans-Bold", "LiberationSans-Bold.ttf"),
    ]
    italic_candidates = [
        ("DejaVuSans-Oblique", "DejaVuSans-Oblique.ttf"),
        ("DejaVuSans-BoldOblique", "DejaVuSans-BoldOblique.ttf"),
        ("LiberationSans-Italic", "LiberationSans-Italic.ttf"),
    ]

    def _find(name_hint: str) -> str | None:
        for d in _CYRILLIC_FONT_DIRS:
            p = os.path.join(d, name_hint)
            if os.path.isfile(p):
                return p
        return None

    regular = bold = italic = None
    for reg_name, file_hint in candidates:
        p = _find(file_hint)
        if p:
            try:
                pdfmetrics.registerFont(TTFont(reg_name, p))
                regular = reg_name
                break
            except Exception:
                continue
    for bold_name, file_hint in bold_candidates:
        p = _find(file_hint)
        if p:
            try:
                pdfmetrics.registerFont(TTFont(bold_name, p))
                bold = bold_name
                break
            except Exception:
                continue
    for ital_name, file_hint in italic_candidates:
        p = _find(file_hint)
        if p:
            try:
                pdfmetrics.registerFont(TTFont(ital_name, p))
                italic = ital_name
                break
            except Exception:
                continue

    if not regular:
        regular = "Helvetica"
    if not bold:
        bold = "Helvetica-Bold"
    if not italic:
        italic = "Helvetica-Oblique"

    pdfmetrics.registerFontFamily(
        regular, normal=regular, bold=bold, italic=italic, boldItalic=bold,
    )
    return regular, bold, italic


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


def _api_base() -> str:
    return os.environ.get("HFABRIC_API_BASE", "http://localhost:8000").rstrip("/")


def _file_url_pdf(session_id: str, path: str) -> str:
    base = _api_base()
    filename = os.path.basename(path)
    return f"{base}/sessions/{session_id}/files/{filename}"


def _chunk_link_pdf(marker: str, cited_refs: dict, session_id: str = "") -> str:
    """Build a clickable link for a chunk-id reference inside PDF body text."""
    chunk = cited_refs.get(marker)
    if chunk is not None:
        url = chunk.meta.get("url")
        if url:
            return f'<a href="{url}">[{marker}]</a>'
        path = chunk.meta.get("path", "")
        if path and session_id:
            return f'<a href="{_file_url_pdf(session_id, path)}">[{marker}]</a>'
    return f"[{marker}]"


def _linkify_pdf_v2(text: str, cited_refs: dict, session_id: str = "") -> str:
    """Like _linkify_pdf but also links local chunks by HTTP file URL."""
    if not text:
        return text

    def repl(m: "re.Match") -> str:
        marker = m.group(1).strip()
        return _chunk_link_pdf(marker, cited_refs, session_id)

    return re.sub(r"\[([^\]\n]+)\]", repl, text)


def write_pdf(result: RunResult, session_id: str) -> str:
    from reportlab.lib.pagesizes import A4

    export_dir = os.path.join("sessions", session_id, "export")
    os.makedirs(export_dir, exist_ok=True)
    path = os.path.join(export_dir, "report.pdf")

    font_reg, font_bold, font_ital = _register_cyrillic_fonts()

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
    h1 = ParagraphStyle("H1c", parent=base["Heading1"], fontName=font_bold, fontSize=16)
    h2 = ParagraphStyle("H2c", parent=base["Heading2"], fontName=font_bold, fontSize=13)
    h3 = ParagraphStyle("H3c", fontName=font_bold, fontSize=11, spaceBefore=6, spaceAfter=3,
                        textColor=colors.HexColor("#1a6b4a"))
    body = ParagraphStyle("BodyC", fontName=font_reg, fontSize=9, leading=12, spaceAfter=4)
    small = ParagraphStyle("SmallC", fontName=font_reg, fontSize=8, leading=10,
                           textColor=colors.grey, spaceAfter=2)

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
            return _linkify_pdf_v2(text, cited_refs, session_id)

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
            story.append(Paragraph("<b>Evidence / Sources:</b>", body))
            for cid, c in cited_refs.items():
                meta = c.meta or {}
                url = meta.get("url")
                doc_name = meta.get("doc_id", c.doc_id or cid)
                page = meta.get("page", "")
                loc = f" стр. {page}" if page else ""
                if url:
                    title = meta.get("title") or url
                    story.append(Paragraph(
                        f'- <a href="{url}">[{cid}]</a> <b>{doc_name}</b>{loc}: {c.text[:200]}', small))
                else:
                    fpath = meta.get("path", "")
                    link = f"<a href=\"{_file_url_pdf(session_id, fpath)}\">[{cid}]</a>" if fpath else f"[{cid}]"
                    story.append(Paragraph(
                        f"- {link} <b>{doc_name}</b>{loc}: {c.text[:200]}", small))
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