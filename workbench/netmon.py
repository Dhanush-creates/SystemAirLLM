"""Network monitor: watches the OS sockets of the workbench and model-server processes.

A background thread samples connections every few seconds and remembers every
remote address that is not on this machine, so a short-lived connection is not missed.
It observes; it does not block. Blocking is done by netguard, the sandbox's
`--network none`, and (in deployment) the firewall or a physical air gap.
"""
from __future__ import annotations

import ipaddress
import json
import threading
import time
from pathlib import Path

import psutil

MODEL_SERVER_NAMES = ("ollama", "vllm", "llama")
INTERVAL = 2.0


def scope(ip: str) -> str:
    addr = ipaddress.ip_address(ip.split("%")[0])
    if addr.is_loopback:
        return "this machine"
    if addr.is_private or addr.is_link_local:
        return "local network"
    return "external"


def _watched() -> dict[int, str]:
    me = psutil.Process()
    procs = [me, *me.children(recursive=True)]
    pids = {}
    for p in procs:
        try:
            pids[p.pid] = p.name()
        except psutil.Error:
            pass
    for p in psutil.process_iter(["name"]):
        name = (p.info["name"] or "").lower()
        if any(s in name for s in MODEL_SERVER_NAMES):
            pids[p.pid] = p.info["name"]
    return pids


def snapshot() -> list[dict]:
    pids = _watched()
    out = []
    try:
        conns = psutil.net_connections(kind="inet")
    except psutil.Error:
        return out
    for c in conns:
        if c.pid in pids and c.raddr:
            out.append({"process": pids[c.pid], "pid": c.pid, "remote": f"{c.raddr.ip}:{c.raddr.port}",
                        "scope": scope(c.raddr.ip), "status": c.status})
    return out


class Monitor:
    def __init__(self, log_path: Path | None = None):
        self.log_path = log_path  # every non-local sighting and blocked attempt is also written here
        self.egress_test: dict | None = None  # result of the last egress test
        self.started = time.strftime("%Y-%m-%d %H:%M:%S")
        self.samples = 0
        self.external: dict[tuple, dict] = {}  # every non-local remote seen since start
        self.blocked: list[dict] = []          # attempts stopped by the egress guard
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self) -> "Monitor":
        if not self._thread.is_alive():
            self._thread.start()
        return self

    def _loop(self):
        while True:
            self.sample()
            time.sleep(INTERVAL)

    def sample(self) -> list[dict]:
        conns = snapshot()
        self.samples += 1
        now = time.strftime("%H:%M:%S")
        for c in conns:
            if c["scope"] != "this machine":
                key = (c["process"], c["remote"])
                if key not in self.external:
                    self._log({"event": "non_local_connection", **c})
                rec = self.external.setdefault(key, {**c, "first_seen": now, "times_seen": 0})
                rec["last_seen"] = now
                rec["times_seen"] += 1
        return conns

    def _log(self, record: dict) -> None:
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **record}) + "\n")

    def record_block(self, target: str, detail: str) -> None:
        self.blocked.append({"time": time.strftime("%H:%M:%S"), "target": target, "detail": detail})
        self._log({"event": "blocked_attempt", "target": target, "detail": detail})

    def watched(self) -> list[str]:
        return sorted(set(_watched().values()))

    def status(self) -> dict:
        conns = snapshot()
        outside = [r for r in self.external.values() if r["scope"] == "external"]
        return {
            "sovereign": not outside,
            "since": self.started,
            "samples": self.samples,
            "connections": conns,
            "non_local_seen": list(self.external.values()),
            "external_count": len(outside),
            "blocked": self.blocked[-50:],
        }
