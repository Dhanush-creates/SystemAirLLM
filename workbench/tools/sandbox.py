"""Python sandbox. Docker with no network when the image is present; local subprocess otherwise."""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from functools import lru_cache
from uuid import uuid4

from . import ToolContext, tool

EXTENDED_IMAGE = "workbench-sandbox:1"  # python + numpy, pandas, sympy, openpyxl (scripts/sandbox.Dockerfile)
BASIC_IMAGE = "python:3.12-slim"        # standard library only
IMAGE = BASIC_IMAGE                     # kept for callers that name the minimum image
TIMEOUT = 60


def _has_image(name: str) -> bool:
    try:
        return subprocess.run(["docker", "image", "inspect", name], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


@lru_cache
def sandbox_image() -> str | None:
    """The best sandbox image present, or None when Docker cannot be used."""
    return next((i for i in (EXTENDED_IMAGE, BASIC_IMAGE) if _has_image(i)), None)


def _docker_ready() -> bool:
    return sandbox_image() is not None


def describe_mode(setting: str) -> str:
    mode = _mode(setting)
    if mode == "local":
        return "a local process with no network isolation (Docker not available)"
    extra = " with numpy, pandas and sympy" if sandbox_image() == EXTENDED_IMAGE else ""
    return f"a Docker container with networking disabled ({sandbox_image()}{extra})"


def _mode(setting: str) -> str:
    if setting in ("docker", "local"):
        return setting
    return "docker" if _docker_ready() else "local"


def _exec(ctx: ToolContext, py_args: list[str]) -> str:
    mode = _mode(ctx.sandbox)
    name = f"wb-{uuid4().hex[:8]}"
    if mode == "docker":
        cmd = ["docker", "run", "--rm", "--name", name, "--network", "none",
               "--memory", "512m", "--cpus", "1", "--pids-limit", "128",
               "-v", f"{ctx.workspace.resolve()}:/work", "-w", "/work", sandbox_image(), "python", *py_args]
    else:
        cmd = [sys.executable, *py_args]
    try:
        # UTF-8 both ways: engineering output is full of symbols (ρ, Δ, °) that the Windows
        # default encoding cannot decode.
        p = subprocess.run(cmd, cwd=ctx.workspace, capture_output=True, timeout=TIMEOUT,
                           encoding="utf-8", errors="replace", env={**os.environ, "PYTHONUTF8": "1"})
    except subprocess.TimeoutExpired:
        if mode == "docker":
            subprocess.run(["docker", "kill", name], capture_output=True)
        return f"ERROR: timed out after {TIMEOUT}s"
    label = "docker, no network" if mode == "docker" else "local, dev only"
    return f"[sandbox: {label}] exit={p.returncode}\n{p.stdout}{p.stderr}"


def _print_last_expression(code: str) -> str:
    """Like a notebook: if the code ends with a bare expression, print its value."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code  # let Python report the error
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        last = tree.body[-1]
        call = last.value
        if not (isinstance(call, ast.Call) and getattr(call.func, "id", "") == "print"):
            last.value = ast.Call(func=ast.Name(id="print", ctx=ast.Load()), args=[call], keywords=[])
            return ast.unparse(ast.fix_missing_locations(tree))
    return code


LIBRARIES = ("numpy, pandas, sympy and openpyxl are installed" if sandbox_image() == EXTENDED_IMAGE
             else "standard library only: no numpy, pandas or sympy")


@tool("run_python",
      f"Run Python code in the sandbox (no network; {LIBRARIES}). "
      "Returns exit code, stdout and stderr. Use print() to show values.",
      code="Python source to run")
def run_python(ctx: ToolContext, code: str) -> str:
    (ctx.workspace / "_run.py").write_text(_print_last_expression(code), encoding="utf-8")
    out = _exec(ctx, ["_run.py"])
    if "ModuleNotFoundError" in out:
        out += f"\n(the sandbox has: {LIBRARIES}. Rewrite the code without the missing module.)"
    if out.rstrip().endswith("exit=0"):
        out += "(the code printed nothing: use print() to show results)"
    return out


@tool("run_tests", "Run all unittest files named test*.py in the workspace, in the sandbox. "
                   "The output shows how many tests ran and whether they passed.")
def run_tests(ctx: ToolContext) -> str:
    return _exec(ctx, ["-m", "unittest", "discover", "-v", "-p", "test*.py"])
