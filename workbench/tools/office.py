"""Deliverable tools: real Word, Excel and PowerPoint files written to the workspace."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from . import ToolContext, tool


def _text(value) -> str:
    """Models send a section as a string or as a list of points; accept both."""
    if isinstance(value, (list, tuple)):
        return "\n".join(f"- {v}" for v in value)
    return str(value or "")


def _list(value):
    return json.loads(value) if isinstance(value, str) else value


def _out(ctx: ToolContext, path: str, ext: str):
    other = Path(path).suffix.lower()
    if other and other != ext:
        raise ValueError(f"this tool only creates {ext} files. For a {other} file use write_file.")
    p = ctx.resolve(path if other else path + ext)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _render(doc, content: str) -> None:
    """Light markdown: '# heading', '- bullet', '1. item', '| a | b |' table rows, paragraphs."""
    rows: list[list[str]] = []

    def flush():
        if not rows:
            return
        table = doc.add_table(rows=len(rows), cols=max(len(r) for r in rows))
        table.style = "Table Grid"
        for i, r in enumerate(rows):
            for j, cell in enumerate(r):
                table.cell(i, j).text = cell
                if i == 0:
                    for run in table.cell(i, j).paragraphs[0].runs:
                        run.bold = True
        rows.clear()

    for line in content.replace("**", "").splitlines():
        s = line.strip()
        if s.startswith("|"):
            if not set(s) <= set("|-: "):  # skip the |---|---| separator row
                rows.append([c.strip() for c in s.strip("|").split("|")])
            continue
        flush()
        if not s:
            continue
        if s.startswith("#"):
            doc.add_heading(s.lstrip("# "), min(len(s) - len(s.lstrip("#")), 3))
        elif s[:2] in ("- ", "* "):
            doc.add_paragraph(s[2:], style="List Bullet")
        elif re.match(r"\d+[.)] ", s):
            doc.add_paragraph(re.sub(r"^\d+[.)] ", "", s), style="List Number")
        else:
            doc.add_paragraph(s)
    flush()


@tool("make_docx",
      "Create a Word document. Content is plain text using '# Heading', '- bullet', '1. item' "
      "and '| a | b |' table rows.",
      path="output .docx path", title="document title", content="document body")
def make_docx(ctx: ToolContext, path: str, title: str, content: str) -> str:
    from docx import Document
    p = _out(ctx, path, ".docx")
    doc = Document()
    doc.add_heading(str(title), 0)
    _render(doc, _text(content))
    doc.save(str(p))
    return f"created Word document {p.relative_to(ctx.workspace.resolve()).as_posix()}"


@tool("make_approval_note",
      "Create a formal approval note as a Word file, in the standard layout with a signature block.",
      path="output .docx path", subject="subject line", background="background paragraph(s)",
      findings="key findings, as text or a list", recommendation="recommended action",
      approval_sought="what approval is requested", reference="optional reference number")
def make_approval_note(ctx: ToolContext, path: str, subject: str, background, findings,
                       recommendation, approval_sought, reference: str = "") -> str:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    p = _out(ctx, path, ".docx")
    doc = Document()
    doc.add_heading("NOTE FOR APPROVAL", 0).alignment = WD_ALIGN_PARAGRAPH.CENTER
    head = doc.add_table(rows=3, cols=2)
    head.style = "Table Grid"
    for i, (k, v) in enumerate([("Reference", reference or "—"), ("Date", time.strftime("%d %B %Y")),
                                ("Subject", subject)]):
        head.cell(i, 0).text, head.cell(i, 1).text = k, str(v)
        head.cell(i, 0).paragraphs[0].runs[0].bold = True
    sections = [("Background", background), ("Key Findings", findings),
                ("Recommendation", recommendation), ("Approval Sought", approval_sought)]
    for n, (name, body) in enumerate(sections, 1):
        doc.add_heading(f"{n}. {name}", 2)
        _render(doc, _text(body))
    doc.add_paragraph()
    sign = doc.add_table(rows=2, cols=3)
    sign.style = "Table Grid"
    for j, role in enumerate(("Prepared by", "Reviewed by", "Approved by")):
        sign.cell(0, j).text = role
        sign.cell(0, j).paragraphs[0].runs[0].bold = True
        sign.cell(1, j).text = "\n\nName:\nDesignation:\nDate:"
    doc.add_paragraph()
    doc.add_paragraph("Drafted with the on-premise AI workbench. Review before signing.").runs[0].italic = True
    doc.save(str(p))
    return f"created approval note {p.relative_to(ctx.workspace.resolve()).as_posix()}"


@tool("make_xlsx",
      "Create an Excel workbook with one sheet.",
      path="output .xlsx path",
      rows='list of rows, each a list of cell values; first row is the header; a string starting with "=" is a formula, e.g. "=SUM(B2:B5)"',
      sheet="optional sheet name")
def make_xlsx(ctx: ToolContext, path: str, rows, sheet: str = "Sheet1") -> str:
    from openpyxl import Workbook
    from openpyxl.styles import Font
    p = _out(ctx, path, ".xlsx")
    wb = Workbook()
    ws = wb.active
    ws.title = str(sheet)[:31]
    rows = _list(rows)
    for row in rows:
        ws.append(list(row) if isinstance(row, (list, tuple)) else [row])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for col in ws.columns:
        width = max(len(str(c.value)) for c in col if c.value is not None) if any(c.value for c in col) else 8
        ws.column_dimensions[col[0].column_letter].width = min(max(10, width + 2), 60)
    wb.save(str(p))
    return f"created Excel workbook {p.relative_to(ctx.workspace.resolve()).as_posix()} with {len(rows)} rows"


@tool("make_pptx",
      "Create a PowerPoint presentation.",
      path="output .pptx path", title="presentation title",
      slides='list of {"title": "slide title", "bullets": ["point", "point"]}')
def make_pptx(ctx: ToolContext, path: str, title: str, slides) -> str:
    from pptx import Presentation
    p = _out(ctx, path, ".pptx")
    prs = Presentation()
    first = prs.slides.add_slide(prs.slide_layouts[0])
    first.shapes.title.text = str(title)
    first.placeholders[1].text = time.strftime("%d %B %Y")
    slides = [s for s in _list(slides) if s.get("bullets")]  # a content slide with no content is dropped
    for s in slides:
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = str(s.get("title", ""))
        bullets = s.get("bullets") or []
        frame = slide.placeholders[1].text_frame
        frame.text = str(bullets[0]) if bullets else ""
        for b in bullets[1:]:
            frame.add_paragraph().text = str(b)
    prs.save(str(p))
    return (f"created presentation {p.relative_to(ctx.workspace.resolve()).as_posix()} "
            f"with a title slide and {len(slides)} content slides")
