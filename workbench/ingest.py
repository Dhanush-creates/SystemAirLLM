"""Input layer: turns any supported file into text, page by page.

Text, Word, Excel and PowerPoint are parsed directly. PDFs use their text layer;
pages without one (scans) and images are read by the local vision model.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

TEXT_EXT = {".txt", ".md", ".csv", ".json", ".py", ".log", ".yaml", ".yml", ".xml", ".html", ".sql"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".gif"}
SUPPORTED = TEXT_EXT | IMAGE_EXT | {".pdf", ".docx", ".xlsx", ".pptx"}

MAX_SIDE = 1600        # longest image side sent to the vision model, in pixels
MAX_VISION_PAGES = 10  # vision reads are slow; cap them per document
MIN_TEXT = 40          # a PDF page with fewer characters than this is treated as a scan
TILE_MIN_IMAGE = 3000  # images this many pixels wide or more are also read in quarters
TILE_MIN_PDF = 1000    # scanned PDF pages this many points wide or more (A3 and up) likewise
DENSE_IMAGE = 3600     # images this wide or more are read in 9 detail views instead of 4
MAX_REPEAT = 3         # a tag may appear a few times on a drawing; more than this is dropped
LOOP_AT = 8            # a line repeated more than this means the vision model was looping

TILE_PROMPT = ("This is one part of a larger engineering drawing or document. Transcribe every tag, label, "
               "line number, value and note exactly as written, one per line, including the letters and numbers "
               "inside instrument circles. Write each item once. No commentary.")

OCR_PROMPT = (
    "Transcribe all text in this image exactly, including handwriting, tables, tag numbers, "
    "stamps and labels. Then, after a line 'DESCRIPTION:', briefly describe any drawing, "
    "diagram or photograph content: equipment, symbols, connections, visible defects."
)

Vision = Callable[[str, bytes], tuple[str, str]]  # (prompt, png) -> (text, model id)


def _render(page, clip=None) -> bytes:
    import pymupdf
    area = clip or page.rect
    zoom = min(3.0, MAX_SIDE / max(area.width, area.height))
    return page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip).tobytes("png")


def _grid(area, n: int) -> list:
    """Split a rectangle into n x n tiles that overlap a little, so a tag on a seam is not cut."""
    import pymupdf
    w, h = area.width / n, area.height / n
    ox, oy = w * 0.08, h * 0.08
    return [pymupdf.Rect(max(area.x0, area.x0 + c * w - ox), max(area.y0, area.y0 + r * h - oy),
                         min(area.x1, area.x0 + (c + 1) * w + ox), min(area.y1, area.y0 + (r + 1) * h + oy))
            for r in range(n) for c in range(n)]


def _tiles(page, is_image: bool) -> list:
    """Large drawings are also read as detail views, so small tags stay legible: 2 x 2, or 3 x 3
    for very large sheets."""
    r = page.rect
    size = max(r.width, r.height)
    if is_image:
        info = page.get_image_info()
        if info:  # true pixel size, whatever resolution the file declares
            size = max(info[0]["width"], info[0]["height"])
        if size < TILE_MIN_IMAGE:
            return []
        return _grid(r, 3 if size >= DENSE_IMAGE else 2)
    return _grid(r, 2) if size >= TILE_MIN_PDF else []


def _clean(text: str) -> tuple[str, bool]:
    """Remove the repetition a vision model falls into on dense drawings (one tag hundreds of times).

    Returns the text with each distinct line kept at most MAX_REPEAT times, and whether a loop was found.
    """
    counts: dict[str, int] = {}
    out, looped = [], False
    for line in text.splitlines():
        key = line.strip()
        if key:
            counts[key] = counts.get(key, 0) + 1
            if counts[key] > MAX_REPEAT:
                looped = looped or counts[key] > LOOP_AT
                continue
        out.append(line)
    return "\n".join(out).strip(), looped


def _read_drawing(page, vision: Vision, is_image: bool) -> tuple[str, str, int]:
    """Overview plus detail views. A view where the model looped is split once more and re-read.
    Returns (text, model id, number of detail views)."""
    text, model = vision(OCR_PROMPT, _render(page))
    text, _ = _clean(text)
    views = 0
    for clip in _tiles(page, is_image):
        detail, looped = _clean(vision(TILE_PROMPT, _render(page, clip))[0])
        parts, views = [detail], views + 1
        if looped:  # too dense for the model at this size: look closer
            for sub in _grid(clip, 2):
                parts.append(_clean(vision(TILE_PROMPT, _render(page, sub))[0])[0])
                views += 1
        text += "\n\n[detail view]\n" + "\n".join(p for p in parts if p)
    return text, model, views


def _pdf_or_image(path: Path, vision: Vision | None, is_image: bool) -> list[dict]:
    import pymupdf
    out, used = [], 0
    with pymupdf.open(path) as doc:
        for n, page in enumerate(doc, 1):
            text = "" if is_image else page.get_text().strip()
            if len(text) >= MIN_TEXT:
                out.append({"page": n, "text": text, "via": "text layer"})
            elif vision is None:
                out.append({"page": n, "text": text or "(no readable text; no vision model available)", "via": "none"})
            elif used >= MAX_VISION_PAGES:
                out.append({"page": n, "text": "(page not read: vision page limit reached)", "via": "none"})
            else:
                used += 1
                text, model, views = _read_drawing(page, vision, is_image)
                via = f"vision model {model}" + (f", in {views} detail views" if views else "")
                out.append({"page": n, "text": text.strip(), "via": via})
    return out


def _docx(path: Path) -> list[dict]:
    from docx import Document
    doc = Document(str(path))
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        parts += [" | ".join(c.text.strip() for c in row.cells) for row in table.rows]
    return [{"page": 1, "text": "\n".join(parts), "via": "docx parser"}]


def _xlsx(path: Path) -> list[dict]:
    from openpyxl import load_workbook
    wb = load_workbook(str(path), read_only=True)  # formulas are kept as formulas
    out = []
    for n, ws in enumerate(wb, 1):
        rows = [" | ".join("" if v is None else str(v) for v in row)
                for row in ws.iter_rows(max_row=200, values_only=True)]
        out.append({"page": n, "text": f"Sheet: {ws.title}\n" + "\n".join(rows), "via": "xlsx parser"})
    wb.close()
    return out


def _pptx(path: Path) -> list[dict]:
    from pptx import Presentation
    out = []
    for n, slide in enumerate(Presentation(str(path)).slides, 1):
        texts = [s.text_frame.text for s in slide.shapes if s.has_text_frame and s.text_frame.text.strip()]
        out.append({"page": n, "text": "\n".join(texts), "via": "pptx parser"})
    return out


def extract(path: Path, vision: Vision | None = None) -> list[dict]:
    """Returns [{'page': n, 'text': str, 'via': how it was read}]."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".pdf" or ext in IMAGE_EXT:
        return _pdf_or_image(path, vision, ext in IMAGE_EXT)
    if ext == ".docx":
        return _docx(path)
    if ext == ".xlsx":
        return _xlsx(path)
    if ext == ".pptx":
        return _pptx(path)
    if ext in TEXT_EXT or not ext:
        return [{"page": 1, "text": path.read_text(encoding="utf-8", errors="replace"), "via": "text"}]
    raise ValueError(f"unsupported file type '{ext}'. Supported: {', '.join(sorted(SUPPORTED))}")


def as_text(pages: list[dict], limit: int | None = None) -> str:
    multi = len(pages) > 1
    text = "\n\n".join((f"[page {p['page']}]\n" if multi else "") + p["text"] for p in pages)
    if limit and len(text) > limit:
        text = text[:limit] + f"\n... (truncated: {len(text) - limit} more characters; use read_document with a page number)"
    return text
