"""System check: verifies every function of the workbench on this machine.

    python -m workbench.doctor            quick checks (no model calls)
    python -m workbench.doctor --full     also calls each model and runs an agent task
    python -m workbench.doctor --pull     download the models recommended for this hardware
"""
from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
PACKAGES = {"fastapi": "fastapi", "uvicorn": "uvicorn", "yaml": "pyyaml", "psutil": "psutil",
            "pymupdf": "pymupdf", "docx": "python-docx", "openpyxl": "openpyxl", "pptx": "python-pptx"}
NET_PROBE = """import socket
try:
    socket.create_connection(("1.1.1.1", 443), timeout=5)
    print("REACHED the internet")
except OSError as e:
    print("BLOCKED:", e)
"""

CHECKS: list[tuple[str, bool, object]] = []


def check(name: str, full: bool = False):
    def register(fn):
        CHECKS.append((name, full, fn))
        return fn
    return register


class Env:
    """Everything the checks need, built on a temporary workspace so nothing real is touched."""

    def __init__(self):
        from .agent import Agent
        from .audit import Audit
        from .kb import KnowledgeBase
        from .registry import Registry
        self.tmp = Path(tempfile.mkdtemp(prefix="wb-check-"))
        self.registry = Registry.load()
        self.agent = Agent(self.registry, workspace=self.tmp / "ws", audit=Audit(self.tmp / "audit.jsonl"),
                           kb=KnowledgeBase(self.tmp / "kb.sqlite"))
        self.ctx = self.agent.context()

    def installed(self, capability: str):
        """Installed models with this capability, smallest first."""
        ok = [m for m in self.registry.usable(capability)
              if not m.escalation_only and self.agent.providers[m.provider].available(m.id)]
        return sorted(ok, key=lambda m: m.tier)


def ollama_exe() -> str | None:
    from .modelserver import ollama_exe as find
    return find()


# ---- quick checks ----

@check("Python version")
def _python(env):
    v = sys.version_info
    ok = v >= (3, 10)
    return (PASS if ok else FAIL), f"Python {v.major}.{v.minor}.{v.micro}", "" if ok else "Install Python 3.10 or newer."


@check("Python packages")
def _packages(env):
    missing = []
    for module, pip_name in PACKAGES.items():
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(pip_name)
    if missing:
        return FAIL, "missing: " + ", ".join(missing), "Run setup.bat."
    return PASS, f"all {len(PACKAGES)} present", ""


@check("Hardware budget")
def _hardware(env):
    r = env.registry
    fits = [m.id for m in r.models if m.vram_gb <= r.vram_gb and not m.escalation_only]
    if not fits:
        return FAIL, f"{r.vram_gb} GB from {r.device}: no model in the registry fits", "Add a smaller model to config/models.yaml."
    return PASS, f"{r.vram_gb} GB from {r.device}; {len(fits)} registry models fit", ""


@check("Model server")
def _server(env):
    from .providers import OpenAIProvider
    down = []
    for name, p in env.agent.providers.items():
        if isinstance(p, OpenAIProvider):
            try:
                p._request("/models", timeout=5)
            except OSError as e:
                down.append(f"{name} ({p.base_url}): {e}")
    if down:
        return FAIL, "; ".join(down), "Start Ollama (start.bat does this), or install it with setup.bat."
    return PASS, "reachable on this machine", ""


@check("Model server stays local")
def _server_local(env):
    from . import modelserver
    ok, why = modelserver.status()
    return (PASS if ok else WARN), why, "" if ok else \
        "Start the workbench with start.bat: it stops the Ollama desktop app and runs the server with cloud features off."


@check("Models installed")
def _models(env):
    have = {c: [m.id for m in env.installed(c)] for c in ("general", "code", "vision")}
    missing_caps = [c for c, ids in have.items() if not ids]
    want = [m.id for m in env.registry.recommended() if not env.agent.providers[m.provider].available(m.id)]
    detail = "; ".join(f"{c}: {', '.join(ids) or 'none'}" for c, ids in have.items())
    fix = "Run: python -m workbench.doctor --pull"
    if not have["general"]:
        return FAIL, detail, fix
    if missing_caps:
        return WARN, detail + f". No {' or '.join(missing_caps)} model: those tasks fall back or fail.", fix
    if want:
        return WARN, detail + f". Recommended but not installed: {', '.join(want)}", fix
    return PASS, detail, ""


@check("Egress guard")
def _guard(env):
    from .netguard import EgressBlocked, check_local
    try:
        check_local("https://1.1.1.1/v1")
    except EgressBlocked:
        check_local("http://127.0.0.1:11434/v1")
        return PASS, "internet endpoint refused, local endpoint accepted", ""
    return FAIL, "an internet endpoint was accepted", "Check workbench/netguard.py."


@check("Sandbox isolation")
def _docker(env):
    from .tools import sandbox
    if env.registry.sandbox == "local":
        return WARN, "config sets sandbox: local (no isolation)", "Set sandbox: auto in config/models.yaml."
    if sandbox.sandbox_image() == sandbox.EXTENDED_IMAGE:
        return PASS, f"Docker image {sandbox.EXTENDED_IMAGE} present (numpy, pandas, sympy)", ""
    if sandbox._docker_ready():
        return WARN, f"only the basic image {sandbox.BASIC_IMAGE} is present: no numpy, pandas or sympy", \
            "Run setup.bat with internet to build the extended sandbox image."
    return WARN, "Docker or its image is not available; code runs as a local process without network isolation", \
        f"Start Docker Desktop, then: docker pull {sandbox.IMAGE}"


@check("Sandbox runs code")
def _sandbox(env):
    from . import tools
    out = tools.run("run_python", {"code": "print(6 * 7)"}, env.ctx)
    ok = "exit=0" in out and "42" in out
    return (PASS if ok else FAIL), out.strip().replace("\n", " "), "" if ok else "See the error text."


@check("Sandbox has no network")
def _sandbox_net(env):
    from . import tools
    out = tools.run("run_python", {"code": NET_PROBE}, env.ctx).strip().replace("\n", " ")
    if "BLOCKED" in out and "docker" in out:
        return PASS, out, ""
    if "BLOCKED" in out:
        return WARN, out + " (blocked because this machine is offline, not by the sandbox)", "Start Docker Desktop."
    return WARN, out, "Start Docker Desktop so code runs with networking disabled."


@check("Input layer: text, PDF, Word, Excel, PowerPoint")
def _inputs(env):
    import pymupdf
    from . import tools
    ws = env.ctx.workspace
    read = lambda name: tools.run("read_document", {"path": name}, env.ctx)
    (ws / "c.txt").write_text("alpha text", encoding="utf-8")
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Hydrotest pressure 15 bar for line L-101, held thirty minutes.")
    doc.save(ws / "c.pdf")
    tools.run("make_docx", {"path": "c.docx", "title": "T", "content": "- beta point"}, env.ctx)
    tools.run("make_xlsx", {"path": "c.xlsx", "rows": [["Item", "Qty"], ["Valve", 4], ["Total", "=SUM(B2:B2)"]]}, env.ctx)
    tools.run("make_pptx", {"path": "c.pptx", "title": "T", "slides": [{"title": "S", "bullets": ["gamma point"]}]}, env.ctx)
    tools.run("make_approval_note", {"path": "c_note.docx", "subject": "S", "background": "B", "findings": ["delta"],
                                     "recommendation": "R", "approval_sought": "A"}, env.ctx)
    expect = {"c.txt": "alpha text", "c.pdf": "Hydrotest", "c.docx": "beta point", "c.xlsx": "=SUM(B2:B2)",
              "c.pptx": "gamma point", "c_note.docx": "Approved by"}
    bad = [name for name, text in expect.items() if text not in read(name)]
    if bad:
        return FAIL, "could not write or read back: " + ", ".join(bad), "Run setup.bat to reinstall packages."
    return PASS, f"{len(expect)} file types written and read back", ""


@check("Knowledge base")
def _kb(env):
    env.agent.kb.add("check.txt", [{"page": 2, "text": "Hot work permits are valid for one shift only."}])
    hits = env.agent.kb.search("hot work permit")
    ok = bool(hits) and hits[0]["page"] == 2
    return (PASS if ok else FAIL), "index and search work" if ok else f"unexpected result: {hits}", ""


@check("Network monitor")
def _netmon(env):
    from .netmon import snapshot
    conns = snapshot()
    outside = sorted({f"{c['process']} -> {c['remote']}" for c in conns if c["scope"] == "external"})
    if outside:
        return WARN, "external connections right now: " + "; ".join(outside), \
            "If a model download is running, wait for it. Otherwise start the workbench with start.bat, " \
            "which runs the model server with its cloud features off."
    return PASS, f"{len(conns)} live connections, none external", ""


# ---- full checks (call the models) ----

def _ping(env, capability: str):
    models = env.installed(capability)
    if not models:
        return WARN, f"no {capability} model installed", "Run: python -m workbench.doctor --pull"
    m = models[0]
    reply = env.agent.providers[m.provider].chat(m.id, [{"role": "user", "content": "Reply with the single word: ready"}])
    ok = bool(reply.strip())
    return (PASS if ok else FAIL), f"{m.id} replied: {reply.strip()[:60]!r}", ""


@check("General model replies", full=True)
def _general(env):
    return _ping(env, "general")


@check("Coding model replies", full=True)
def _code(env):
    return _ping(env, "code")


@check("Vision model reads an image", full=True)
def _vision(env):
    import pymupdf
    if not env.installed("vision"):
        return WARN, "no vision model installed: scans and images cannot be read", "Run: python -m workbench.doctor --pull"
    page = pymupdf.open().new_page(width=400, height=120)
    page.insert_text((30, 70), "VALVE TAG V-2047", fontsize=28)
    text, model = env.agent.vision("Transcribe the text in this image.", page.get_pixmap().tobytes("png"))
    ok = "2047" in text
    return (PASS if ok else FAIL), f"{model} read: {text.strip()[:80]!r}", "" if ok else "The vision model misread a clear image."


@check("Agent task end to end", full=True)
def _agent(env):
    events = list(env.agent.run("Create a file named check.txt containing exactly the word verified."))
    last = events[-1]
    made = next(iter(env.ctx.workspace.rglob("check.txt")), None)
    ok = last["type"] == "final" and made is not None and "verified" in made.read_text(encoding="utf-8").lower()
    detail = f"{events[0].get('model', '?')} finished in {last.get('steps', '?')} steps" if ok else f"ended with: {last}"
    return (PASS if ok else FAIL), detail, "" if ok else "Run again; if it keeps failing, install a larger model."


@check("Agent team task end to end", full=True)
def _team(env):
    from .orchestrator import Orchestrator
    events = list(Orchestrator(env.agent).run("Calculate 15 percent of 2400 and show the calculation."))
    last = events[-1]
    agents = [e["agent"] for e in events if e["type"] == "agent_done"]
    ok = last["type"] == "final" and "360" in last.get("answer", "") and "unverified" not in last
    detail = f"agents {agents} gave a checked result of 360" if ok else f"agents {agents}; ended with: {str(last)[:200]}"
    return (PASS if ok else FAIL), detail, "" if ok else "Run again; if it keeps failing, install a larger model."


def run(full: bool = False) -> list[dict]:
    results = []
    try:
        env = Env()
    except Exception as e:
        return [{"check": "Startup", "status": FAIL, "detail": f"{type(e).__name__}: {e}", "fix": "Run setup.bat."}]
    for name, is_full, fn in CHECKS:
        if is_full and not full:
            continue
        try:
            status, detail, fix = fn(env)
        except Exception as e:
            status, detail, fix = FAIL, f"{type(e).__name__}: {e}", "See the error text."
        results.append({"check": name, "status": status, "detail": detail, "fix": fix})
    shutil.rmtree(env.tmp, ignore_errors=True)
    return results


def pull() -> int:
    """Download the models recommended for this hardware that are not installed yet."""
    env = Env()
    exe = ollama_exe()
    if not exe:
        print("Ollama is not installed. Run setup.bat first.")
        return 1
    want = [m for m in env.registry.recommended() if not env.agent.providers[m.provider].available(m.id)]
    print(f"Hardware budget: {env.registry.vram_gb} GB ({env.registry.device})")
    if not want:
        print("All recommended models are already installed.")
        return 0
    print("Downloading:", ", ".join(m.id for m in want))
    failed = [m.id for m in want if subprocess.run([exe, "pull", m.id]).returncode != 0]
    if failed:
        print("FAILED to download:", ", ".join(failed))
    return 1 if failed else 0


def main() -> int:
    if "--pull" in sys.argv:
        return pull()
    results = run(full="--full" in sys.argv)
    for r in results:
        print(f"[{r['status']}] {r['check']}: {r['detail']}")
        if r["fix"]:
            print(f"       fix: {r['fix']}")
    counts = {s: sum(r["status"] == s for r in results) for s in (PASS, WARN, FAIL)}
    print(f"\n{counts[PASS]} passed, {counts[WARN]} warnings, {counts[FAIL]} failed")
    return 1 if counts[FAIL] else 0


if __name__ == "__main__":
    sys.exit(main())
