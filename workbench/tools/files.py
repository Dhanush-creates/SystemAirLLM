"""File tools, confined to the task workspace."""
from __future__ import annotations

from . import ToolContext, tool


@tool("list_files", "List files in the workspace.", path="folder, '.' for the root")
def list_files(ctx: ToolContext, path: str = ".") -> str:
    root = ctx.resolve(path)
    names = sorted(p.name + ("/" if p.is_dir() else "") for p in root.iterdir())
    return "\n".join(names) or "(empty)"


@tool("read_file", "Read a text file from the workspace.", path="file path")
def read_file(ctx: ToolContext, path: str) -> str:
    return ctx.resolve(path).read_text(encoding="utf-8", errors="replace")


@tool("write_file", "Create or overwrite a text file in the workspace.", path="file path", content="full file text")
def write_file(ctx: ToolContext, path: str, content: str) -> str:
    p = ctx.resolve(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"wrote {len(content)} characters to {path}"
