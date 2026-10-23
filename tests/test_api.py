"""API tests: a real server on a free port, driven over HTTP, with a scripted mock model.

Run: python tests/test_api.py
"""
import json
import socket
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn

from workbench import api
from workbench.agent import Agent
from workbench.audit import Audit
from workbench.kb import KnowledgeBase
from workbench.orchestrator import Orchestrator
from workbench.providers import MockProvider
from workbench.registry import Registry
from test_core import CFG

TMP = Path(tempfile.mkdtemp())
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def script(model, messages):
    last = messages[-1]["content"]
    if "Observation from write_file" in last:
        return '{"final": "Saved hello.txt."}'
    if "hello.txt" in messages[1]["content"] and len(messages) == 2 and "Earlier" not in messages[1]["content"]:
        return json.dumps({"tool": "write_file", "args": {"path": "hello.txt", "content": "hi"}})
    return json.dumps({"final": "Follow-up seen." if "Earlier in this conversation" in messages[1]["content"] else "ok"})


def start_server() -> str:
    agent = Agent(Registry(CFG), {"mock": MockProvider(script)}, workspace=TMP / "ws",
                  audit=Audit(TMP / "audit.jsonl"), kb=KnowledgeBase(TMP / "kb.sqlite"))
    team = Orchestrator(agent)
    api.agent, api.team, api.KB_FILES = (lambda: agent), (lambda: team), TMP / "kb_files"
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(api.app, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            OPENER.open(base + "/network", timeout=1)
            return base
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("server did not start")


BASE = start_server()


def call(path, data=None, method=None, ctype="application/json"):
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={"Content-Type": ctype})
    return OPENER.open(req, timeout=60)


def js(path, **kw):
    return json.load(call(path, **kw))


def status(path, **kw):
    try:
        return call(path, **kw).status
    except urllib.error.HTTPError as e:
        return e.code


def chat(message, attachments=(), session=None):
    body = json.dumps({"message": message, "attachments": list(attachments), "session": session}).encode()
    return [json.loads(line) for line in call("/chat", data=body, method="POST")]


def test_ui_and_listings():
    page = call("/").read().decode("utf-8")
    assert "Sovereign Workbench" in page and "http://" not in page.replace("http://www.w3.org", "")  # no external resources
    assert [a["name"] for a in js("/agents")] == ["reader", "researcher", "analyst", "coder", "writer", "responder"]
    models = js("/models")
    assert models["vram_gb"] == 12 and any(m["id"] == "big" and m["available"] for m in models["models"])


def test_upload_rules():
    up = js("/upload?name=note.txt", data=b"pump P-101A", method="POST", ctype="application/octet-stream")
    assert up == {"path": "uploads/note.txt", "size": 11}
    assert status("/upload?name=evil.exe", data=b"x", method="POST") == 415
    # A path in the name is reduced to the file name; nothing is written outside uploads/.
    up = js("/upload?name=" + urllib.parse.quote("../../escape.txt"), data=b"x", method="POST")
    assert up["path"] == "uploads/escape.txt" and not (TMP / "escape.txt").exists()
    assert status("/upload?name=big.txt", data=b"x" * (api.MAX_UPLOAD + 1), method="POST") == 413


def test_chat_creates_file_and_download_is_confined():
    events = chat("Create hello.txt containing hi", session="s1")
    assert events[0]["type"] == "route" and events[-1] == {"type": "final", "model": "small", "steps": 2,
                                                          "answer": "Saved hello.txt."}
    path = f"{events[0]['workspace']}/hello.txt"
    assert path in [f["path"] for f in js("/files")]
    assert call("/files/" + path).read() == b"hi"
    assert status("/files/" + urllib.parse.quote("../audit.jsonl", safe="")) in (403, 404)
    assert status("/files/tasks/none/missing.txt") == 404


def test_conversation_memory_over_http():
    assert chat("And now?", session="s1")[-1]["answer"] == "Follow-up seen."   # same session: remembers
    assert chat("And now?", session="s2")[-1]["answer"] == "ok"               # new session: does not
    body = json.dumps({"message": "x", "session": "../../etc"}).encode()
    assert status("/chat", data=body, method="POST") == 400                   # session is a folder name


def test_knowledge_base_over_http():
    r = js("/kb/upload?name=sop.txt", data=b"Hot work permits are valid for one shift only.", method="POST",
           ctype="application/octet-stream")
    assert r["doc"] == "sop.txt" and r["chunks"] == 1
    assert js("/kb") == [{"doc": "sop.txt", "chunks": 1}]
    assert js("/kb/search?q=permit%20validity")[0]["doc"] == "sop.txt"
    assert status("/kb/upload?name=bad.exe", data=b"x", method="POST") == 422
    call("/kb/sop.txt", method="DELETE")
    assert js("/kb") == []


def test_network_endpoints_and_report():
    net = js("/network")
    assert {"sovereign", "connections", "non_local_seen", "blocked", "samples"} <= set(net)
    html = call("/network/report").read().decode("utf-8")
    assert "Sovereignty evidence report" in html and "Where the models run" in html
    assert any(e["type"] == "final" for e in js("/audit?n=50"))


def test_second_request_waits_its_turn():
    api._busy.acquire()  # pretend a task is running
    out = []
    t = threading.Thread(target=lambda: out.extend(chat("hello", session="s3")))
    t.start()
    time.sleep(0.5)
    assert t.is_alive()  # still waiting
    api._busy.release()
    t.join(20)
    assert out[0]["type"] == "queued" and out[-1]["type"] == "final"


if __name__ == "__main__":
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_")]
    for name, fn in tests:
        fn()
        print("PASS", name)
    print(f"\n{len(tests)} passed")
