"""Tool registry. A tool is a function (ctx, **args) -> str registered with @tool."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass
class Tool:
    name: str
    description: str
    params: dict[str, str]
    fn: Callable[..., str]
    group: str = ""


@dataclass
class ToolContext:
    workspace: Path
    sandbox: str = "auto"
    vision: Callable | None = None  # (prompt, png bytes) -> (text, model id)
    kb: object | None = None        # KnowledgeBase

    def resolve(self, path: str) -> Path:
        """Resolve a path inside the workspace; anything outside is refused."""
        root = self.workspace.resolve()
        p = (root / path).resolve()
        if p != root and root not in p.parents:
            raise PermissionError(f"path outside workspace: {path}")
        return p


TOOLS: dict[str, Tool] = {}


def tool(name: str, description: str, **params: str):
    def register(fn):
        group = fn.__module__.rsplit(".", 1)[-1]  # files | sandbox | documents | office
        TOOLS[name] = Tool(name, description, params, fn, group)
        return fn
    return register


def describe(exclude=(), only=None) -> str:
    """Tool list for a prompt. `only` = tool names to show; `exclude` = tool groups to hide."""
    return "\n".join(
        f"- {t.name}({', '.join(f'{k}: {v}' for k, v in t.params.items())}) — {t.description}"
        for t in TOOLS.values() if t.group not in exclude and (only is None or t.name in only)
    )


def run(name: str, args: dict, ctx: ToolContext) -> str:
    if name not in TOOLS:
        return f"ERROR: unknown tool '{name}'. Available: {', '.join(TOOLS)}"
    try:
        return str(TOOLS[name].fn(ctx, **args))
    except Exception as e:  # the agent must see every failure as an observation
        return f"ERROR: {type(e).__name__}: {e}"


from . import files, sandbox, documents, office  # noqa: E402,F401  (registers the tools)
