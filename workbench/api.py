"""HTTP API and web UI. Run: uvicorn workbench.api:app --host 127.0.0.1 --port 8000"""
from __future__ import annotations

import json
import re
import threading
import time
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel

from . import doctor, ingest, report, tools
from .tools import sandbox
from .agent import Agent
from .netguard import EgressBlocked
from .netmon import Monitor
from .orchestrator import Orchestrator
from .providers import OpenAIProvider
from .registry import ROOT, Registry

monitor = Monitor(ROOT / "logs" / "network.jsonl")


@asynccontextmanager
async def _lifespan(_app):
    monitor.start()
    yield


app = FastAPI(title="Sovereign Workbench", lifespan=_lifespan)
KB_FILES = ROOT / "data" / "kb_files"
MAX_UPLOAD = 50 * 1024 * 1024
SESSION_RE = re.compile(r"[A-Za-z0-9_-]{1,40}")
_busy = threading.Lock()

CANARY_CODE = """import socket
try:
    socket.create_connection(("1.1.1.1", 443), timeout=5)
    print("REACHED the internet")
except OSError as e:
    print("BLOCKED:", e)
"""


@lru_cache
def agent() -> Agent:
    return Agent(Registry.load())


@lru_cache
def team() -> Orchestrator:
    return Orchestrator(agent())


def _safe_name(name: str) -> str:
    name = Path(name).name
    if not name or name.startswith("."):
        raise HTTPException(400, "invalid file name")
    return name


@app.get("/")
def ui():
    return FileResponse(Path(__file__).with_name("ui.html"))


# ---- agent ----

class ChatIn(BaseModel):
    message: str
    attachments: list[str] = []
    session: str | None = None  # same value on every turn of one conversation


@app.post("/chat")
def chat(body: ChatIn):
    """Streams agent events as newline-delimited JSON."""
    if body.session is not None and not SESSION_RE.fullmatch(body.session):
        raise HTTPException(400, "invalid session id")  # it becomes a folder name

    def events():
        # One GPU, one task at a time: a second request waits its turn.
        if not _busy.acquire(blocking=False):
            yield json.dumps({"type": "queued", "message": "Another task is running; this one starts when it finishes."}) + "\n"
            _busy.acquire()
        try:
            for e in team().run(body.message, tuple(body.attachments), body.session):
                yield json.dumps(e) + "\n"
        finally:
            _busy.release()

    return StreamingResponse(events(), media_type="application/x-ndjson")


@app.get("/agents")
def agents():
    out = []
    for a in team().defs.values():
        try:
            model = agent().router.route_for(a.capability, "high").model.id
        except Exception:
            model = None
        out.append({"name": a.name, "title": a.title, "job": a.job, "capability": a.capability,
                    "tools": a.tools, "checks": a.checks, "model": model})
    return out


# ---- workspace files ----

@app.post("/upload")
async def upload(request: Request, name: str):
    """Raw file body; saved to workspace/uploads/<name>."""
    name = _safe_name(name)
    if Path(name).suffix.lower() not in ingest.SUPPORTED:
        raise HTTPException(415, f"unsupported file type. Supported: {', '.join(sorted(ingest.SUPPORTED))}")
    data = await request.body()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, f"file is larger than {MAX_UPLOAD // 2**20} MB")
    dest = agent().workspace / "uploads" / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return {"path": f"uploads/{name}", "size": dest.stat().st_size}


@app.get("/files")
def files():
    root = agent().workspace.resolve()
    out = [{"path": p.relative_to(root).as_posix(), "size": p.stat().st_size, "mtime": p.stat().st_mtime}
           for p in root.rglob("*")
           if p.is_file() and not p.name.startswith("_") and "__pycache__" not in p.parts]
    return sorted(out, key=lambda f: -f["mtime"])


@app.get("/files/{path:path}")
def download(path: str):
    try:
        p = agent().context().resolve(path)
    except PermissionError:
        raise HTTPException(403, "outside workspace")
    if not p.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(p, filename=p.name)


# ---- knowledge base ----

@app.get("/kb")
def kb_list():
    return agent().kb.documents()


@app.post("/kb/upload")
async def kb_upload(request: Request, name: str):
    name = _safe_name(name)
    KB_FILES.mkdir(parents=True, exist_ok=True)
    dest = KB_FILES / name
    dest.write_bytes(await request.body())

    def index():
        pages = ingest.extract(dest, agent().vision)
        return agent().kb.add(name, pages), len(pages), sorted({p["via"] for p in pages})

    try:
        chunks, pages, via = await run_in_threadpool(index)
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(422, f"could not read {name}: {e}")
    return {"doc": name, "pages": pages, "chunks": chunks, "via": via}


@app.get("/kb/search")
def kb_search(q: str):
    return agent().kb.search(q, 5)


@app.delete("/kb/{name}")
def kb_delete(name: str):
    name = _safe_name(name)
    agent().kb.remove(name)
    (KB_FILES / name).unlink(missing_ok=True)
    return {"removed": name}


# ---- models, audit, network ----

@app.get("/models")
def models():
    a = agent()
    return {
        "profile": a.registry.profile,
        "vram_gb": a.registry.vram_gb,
        "device": a.registry.device,
        "recommended": [m.id for m in a.registry.recommended()],
        "models": [
            {"id": m.id, "provider": m.provider, "capabilities": m.capabilities, "tier": m.tier,
             "vram_gb": m.vram_gb, "context": m.context, "escalation_only": m.escalation_only,
             "fits": m.vram_gb <= a.registry.vram_gb,
             "available": a.providers[m.provider].available(m.id)}
            for m in a.registry.models
        ],
    }


@app.get("/doctor")
def system_check(full: bool = False):
    """Runs the system check. full=true also calls each model, which takes a few minutes."""
    return doctor.run(full)


@app.get("/audit")
def audit(n: int = 200):
    return agent().audit.tail(n)


@app.get("/network")
def network():
    return monitor.status()


@app.post("/network/canary")
def canary():
    """Deliberately try to reach the internet two ways and report whether each was stopped."""
    results = []
    target = "https://1.1.1.1/v1"
    try:
        OpenAIProvider(target)
        results.append({"test": "Point the model client at an internet address", "blocked": False,
                        "detail": "NOT BLOCKED: the egress guard accepted an external endpoint"})
    except EgressBlocked as e:
        monitor.record_block(target, str(e))
        results.append({"test": "Point the model client at an internet address", "blocked": True, "detail": str(e)})

    out = tools.run("run_python", {"code": CANARY_CODE}, agent().context())
    results.append({"test": "Open an internet connection from inside the code sandbox",
                    "blocked": "BLOCKED" in out and "REACHED" not in out, "detail": out.strip()})
    for r in results:
        agent().audit.log("canary", {"type": "canary", **r})
    monitor.egress_test = {"time": time.strftime("%d %B %Y, %H:%M:%S"), "results": results}
    return results


@app.post("/network/firewall-test")
def firewall_test():
    """Checks the firewall lockdown: the workbench process itself tries one outbound connection.

    Without lockdown.bat (or an unplugged network) this attempt succeeds; that is expected, and it
    is recorded as a deliberate test.
    """
    import socket
    try:
        socket.create_connection(("1.1.1.1", 443), timeout=5).close()
        blocked, detail = False, "the connection to 1.1.1.1:443 succeeded: no firewall lockdown is active"
    except OSError as e:
        blocked, detail = True, f"the connection to 1.1.1.1:443 failed: {e}"
    result = {"test": "Outbound connection from the workbench process itself", "blocked": blocked, "detail": detail}
    monitor._log({"event": "deliberate_firewall_test", **result})
    agent().audit.log("canary", {"type": "canary", **result})
    return result


@app.get("/network/report", response_class=HTMLResponse)
def network_report():
    """Printable evidence page."""
    a = agent()
    return report.build(monitor.status(), monitor, a.registry, sandbox.describe_mode(a.registry.sandbox),
                        a.audit.tail(5000))
