"""Sovereignty evidence report: one printable page showing that the workbench stays on this machine."""
from __future__ import annotations

import platform
import time
from html import escape

from .netguard import EgressBlocked, check_local

CSS = """body{font:14px/1.5 'Segoe UI',system-ui,sans-serif;max-width:900px;margin:32px auto;padding:0 20px;color:#17212b}
h1{font-size:22px;margin-bottom:4px}h2{font-size:15px;margin:26px 0 8px;border-bottom:1px solid #dde3e8;padding-bottom:4px}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #e6eaee;vertical-align:top}
th{color:#5d6b78;font-size:12px}.ok{color:#1b7f4b;font-weight:600}.bad{color:#b3261e;font-weight:600}.dim{color:#5d6b78}
.verdict{font-size:18px;font-weight:600;padding:12px 16px;border-radius:8px;margin:14px 0}
.verdict.ok{background:#e4f4ea}.verdict.bad{background:#fbe9e7}code{font-family:Consolas,monospace;font-size:12px}
@media print{body{margin:0}}"""


def _table(headers: list[str], rows: list[list], empty: str) -> str:
    if not rows:
        return f'<p class="dim">{escape(empty)}</p>'
    head = "".join(f"<th>{escape(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><tr>{head}</tr>{body}</table>"


def _flag(ok: bool, yes: str, no: str) -> str:
    return f'<span class="{"ok" if ok else "bad"}">{escape(yes if ok else no)}</span>'


def build(status: dict, monitor, registry, sandbox_mode: str, audit: list[dict]) -> str:
    e = lambda v: escape(str(v))
    endpoints = []
    for name, cfg in registry.providers.items():
        if cfg.get("type") != "openai":
            continue
        try:
            check_local(cfg["base_url"], registry.allow_private_network)
            local = True
        except EgressBlocked:
            local = False
        endpoints.append([e(name), f"<code>{e(cfg['base_url'])}</code>", _flag(local, "on this machine", "NOT local")])

    outside = [r for r in status["non_local_seen"] if r["scope"] == "external"]
    test = monitor.egress_test
    sessions = len({a["session"] for a in audit})
    verdict_ok = status["sovereign"]
    parts = [
        f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>Sovereignty evidence report</title>"
        f"<style>{CSS}</style></head><body>",
        "<h1>Sovereignty evidence report</h1>",
        f"<div class='dim'>Sovereign Workbench · machine <b>{e(platform.node())}</b> · generated "
        f"{time.strftime('%d %B %Y, %H:%M:%S')}</div>",
        f"<div class='verdict {'ok' if verdict_ok else 'bad'}'>"
        + ("No connection to an address outside this machine was observed."
           if verdict_ok else f"{len(outside)} connection(s) to external addresses were observed.") + "</div>",

        "<h2>1. Where the models run</h2>",
        _table(["Provider", "Endpoint", "Location"], endpoints, "No model endpoints configured."),
        "<p class='dim'>The workbench refuses to start with a model endpoint that is not on this machine.</p>",

        "<h2>2. Monitoring period</h2>",
        _table(["Monitoring since", "Checks run", "Processes watched", "Agent events logged", "Conversations"],
               [[e(status["since"]), e(status["samples"]), e(", ".join(monitor.watched())), e(len(audit)), e(sessions)]], ""),

        "<h2>3. Connections to addresses outside this machine</h2>",
        _table(["Process", "Remote address", "Where", "First seen", "Last seen", "Times seen"],
               [[e(r["process"]), f"<code>{e(r['remote'])}</code>", _flag(r["scope"] != "external", r["scope"], "external"),
                 e(r["first_seen"]), e(r["last_seen"]), e(r["times_seen"])] for r in status["non_local_seen"]],
               "None. Every connection observed stayed on this machine."),

        "<h2>4. Connections open right now</h2>",
        _table(["Process", "PID", "Remote address", "Where", "State"],
               [[e(c["process"]), e(c["pid"]), f"<code>{e(c['remote'])}</code>",
                 _flag(c["scope"] == "this machine", c["scope"], c["scope"]), e(c["status"])] for c in status["connections"]],
               "No open connections."),

        "<h2>5. Egress test</h2>",
        (_table(["Deliberate attempt", "Result", "Detail"],
                [[e(r["test"]), _flag(r["blocked"], "Blocked", "NOT blocked"), f"<code>{e(r['detail'])}</code>"]
                 for r in test["results"]], "") + f"<p class='dim'>Run at {e(test['time'])}.</p>")
        if test else "<p class='dim'>Not run in this session. Use “Run egress test” on the Network monitor screen.</p>",

        "<h2>6. Code sandbox</h2>",
        f"<p>Code written by the agents runs in: <b>{e(sandbox_mode)}</b>.</p>",

        "<h2>7. What this report does and does not prove</h2>",
        "<p class='dim'>The monitor reads the operating system's connection table for the workbench and model-server "
        "processes every 2 seconds, so a connection shorter than that could be missed. It observes; it does not block. "
        "Docker containers are not visible to it; the sandbox is started with networking disabled, which section 5 tests. "
        "For enforcement, apply the outbound firewall rules (<code>lockdown.bat</code>) or disconnect the network.</p>",
        "</body></html>",
    ]
    return "".join(parts)
