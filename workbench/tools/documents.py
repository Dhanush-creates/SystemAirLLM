"""Document reading and knowledge-base search tools."""
from __future__ import annotations

from .. import ingest
from . import ToolContext, tool


@tool("read_document",
      "Read any workspace file as text: PDF (scanned pages are read by the vision model), "
      "image, Word, Excel, PowerPoint or text.",
      path="file path", page="optional page number")
def read_document(ctx: ToolContext, path: str, page=None) -> str:
    pages = ingest.extract(ctx.resolve(path), ctx.vision)
    if page is not None:
        pages = [p for p in pages if p["page"] == int(page)]
        if not pages:
            return f"ERROR: no page {page}"
    return ingest.as_text(pages)


@tool("search_kb",
      "Search the organisation's knowledge base (manuals, SOPs, past correspondence). "
      "Returns passages with their source; cite them as [document p.N].",
      query="search words")
def search_kb(ctx: ToolContext, query: str) -> str:
    if ctx.kb is None:
        return "ERROR: knowledge base not configured"
    hits = ctx.kb.search(query)
    return "\n\n".join(f"[{h['doc']} p.{h['page']}] {h['text']}" for h in hits) or "No matching passages."
