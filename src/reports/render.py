"""PDF rendering (week 7) with ReportLab Platypus.

Renders the aggregated task stats into a clean two-column-free A4 layout:
summary block, status breakdown, tasks created per day (last 14), tasks by
hour of day, and the ten most recent tasks. Empty data renders an explicit
note instead of blank tables.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from reportlab.lib import colors
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

INK = colors.HexColor("#1A1A1A")
GREY = colors.HexColor("#555555")
RULE = colors.HexColor("#DDDDDD")
ACCENT = colors.HexColor("#E8EEF5")

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "TitleX", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=26, leading=30, textColor=INK, spaceAfter=2,
        ),
        "subtitle": ParagraphStyle(
            "SubtitleX", parent=base["Normal"], fontName="Helvetica",
            fontSize=10, leading=14, textColor=GREY, spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "H2X", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=13, leading=16, textColor=INK, spaceBefore=14, spaceAfter=4,
        ),
        "cell": ParagraphStyle(
            "CellX", parent=base["Normal"], fontName="Helvetica",
            fontSize=9, leading=11, textColor=INK,
        ),
        "cell_head": ParagraphStyle(
            "CellHeadX", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=9, leading=11, textColor=colors.white,
        ),
        "note": ParagraphStyle(
            "NoteX", parent=base["Normal"], fontName="Helvetica-Oblique",
            fontSize=9, leading=12, textColor=GREY,
        ),
    }


def _stat_block(st, totals: Dict) -> Table:
    cells = [
        ("Total tasks", str(totals["total"])),
        ("Completed", str(totals["completed"])),
        ("Open", str(totals["open"])),
    ]
    rate = totals.get("completion_rate")
    cells.append(("Completion rate", f"{rate:.1f}%" if rate is not None else "-"))
    data = [[Paragraph(k, st["cell_head"]), Paragraph(v, st["cell"])] for k, v in cells]
    table = Table(data, colWidths=[60 * mm, 34 * mm, 60 * mm, 34 * mm], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), ACCENT),
        ("BACKGROUND", (1, 0), (1, -1), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def _simple_table(st, header: List[str], rows: List[Dict], key_columns: List[str]) -> Table:
    data = [[Paragraph(h, st["cell_head"]) for h in header]]
    for row in rows:
        values = [Paragraph(str(row[k]), st["cell"]) for k in key_columns]
        data.append(values)
    table = Table(data, colWidths=[70 * mm, 70 * mm], hAlign="LEFT", repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ACCENT]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def _or_note(st, rows: List, note: str):
    if rows:
        return _simple_table(st, [k.title() for k in rows[0]], rows, list(rows[0]))
    return Paragraph(note, st["note"])


def _footer(canvas, doc):
    """Page footer: rule line, job id (left), generated timestamp (right)."""
    canvas.saveState()
    canvas.setStrokeColor(RULE)
    canvas.line(MARGIN, 14 * mm, PAGE_W - MARGIN, 14 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(GREY)
    canvas.drawString(MARGIN, 9 * mm, getattr(doc, "job_label", "report"))
    canvas.drawRightString(PAGE_W - MARGIN, 9 * mm, f"Generated {doc.generated_at}")
    canvas.restoreState()


def render_tasks_pdf(stats: Dict, out_path: Path, job_id: Optional[str] = None) -> Path:
    """Render the aggregated stats into a PDF file; returns the file path."""
    st = _styles()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    totals = stats["totals"]
    label = f"report: {job_id}" if job_id else "report: tasks"
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=20 * mm,
        title="Task status report",
        author="FlyRank Task API",
    )
    doc.generated_at = now
    doc.job_label = label

    story = [
        Paragraph("Task status report", st["title"]),
        Paragraph(
            f"Weekly status report built from the task database. "
            f"Generated {now}. Job id: {job_id or '(direct render)'}.",
            st["subtitle"],
        ),
        Spacer(1, 4 * mm),
    ]

    if totals["total"] == 0:
        story.append(
            Paragraph(
                "No tasks in the database yet. Create tasks via POST /tasks and "
                "regenerate this report.",
                st["note"],
            )
        )
        doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
        return out_path

    story.append(Paragraph("Summary", st["h2"]))
    story.append(_stat_block(st, {**totals, "completion_rate": stats["completion_rate"]}))

    story.append(Paragraph("Tasks by status", st["h2"]))
    story.append(
        _simple_table(st, ["State", "Tasks"], stats["by_status"], ["state", "count"])
    )

    story.append(Paragraph(f"Tasks created per day (last 14 days, UTC)", st["h2"]))
    story.append(
        _or_note(
            st,
            stats["per_day"],
            "No tasks were created in the last 14 days.",
        )
    )

    story.append(Paragraph("Tasks by hour of day (UTC)", st["h2"]))
    story.append(
        _or_note(
            st,
            stats["by_hour"],
            "No tasks to bucket by hour.",
        )
    )

    story.append(Paragraph("Most recent tasks", st["h2"]))
    story.append(
        _simple_table(st, ["Id", "Title"], stats["recents"], ["id", "title"])
        if stats["recents"]
        else Paragraph("No tasks yet.", st["note"])
    )

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return out_path