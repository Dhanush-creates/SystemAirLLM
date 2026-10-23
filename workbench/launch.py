"""Starts everything: the model server if it is not running, the API, and the browser.

    python -m workbench.launch
"""
from __future__ import annotations

import json
import socket
import sys
import threading
import urllib.request
import webbrowser

from . import modelserver

HOST, PORT = "127.0.0.1", 8000
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _is_workbench(port: int) -> bool:
    """True when the program already listening on this port is this workbench."""
    try:
        agents = json.load(_opener.open(f"http://{HOST}:{port}/agents", timeout=3))
        return isinstance(agents, list) and any(a.get("name") == "writer" for a in agents)
    except (OSError, ValueError, AttributeError):
        return False


def pick_port() -> tuple[int, bool]:
    """The first usable port from 8000 up. Returns (port, already_running)."""
    for port in range(PORT, PORT + 10):
        with socket.socket() as s:
            in_use = s.connect_ex((HOST, port)) == 0
        if not in_use:
            return port, False
        if _is_workbench(port):
            return port, True
        print(f"Port {port} is used by another program; trying the next one.")
    raise SystemExit(f"No free port between {PORT} and {PORT + 9}. Close a program that uses one of them.")


def main() -> int:
    print(modelserver.ensure(), flush=True)
    port, running = pick_port()
    url = f"http://{HOST}:{port}"
    if running:
        print(f"The workbench is already running at {url}.")
        webbrowser.open(url)
        return 0
    import uvicorn
    threading.Timer(2.0, webbrowser.open, [url]).start()
    print(f"Workbench: {url}   (close this window to stop)", flush=True)
    uvicorn.run("workbench.api:app", host=HOST, port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
