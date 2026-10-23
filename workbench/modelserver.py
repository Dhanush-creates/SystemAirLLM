"""Keeps the local model server (Ollama) from talking to the internet.

Measured on Ollama 0.35: the server opens a connection to an external address by itself
(its cloud features), and the desktop app checks for updates. Started with
OLLAMA_NO_CLOUD=1 and without the desktop app, the server made no external connection.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

import psutil

URL = "http://127.0.0.1:11434/api/version"
ENV = {"OLLAMA_NO_CLOUD": "1"}
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def ollama_exe() -> str | None:
    found = shutil.which("ollama")
    if found:
        return found
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
    return str(local) if local.is_file() else None


def up() -> bool:
    try:
        _opener.open(URL, timeout=2)
        return True
    except OSError:
        return False


def _processes() -> tuple[list[psutil.Process], list[psutil.Process]]:
    """(desktop app processes, server processes)."""
    apps, servers = [], []
    for p in psutil.process_iter(["name", "cmdline"]):
        name = (p.info["name"] or "").lower()
        if "ollama" not in name:
            continue
        if "app" in name:
            apps.append(p)
        elif "serve" in (p.info["cmdline"] or []):
            servers.append(p)
    return apps, servers


def _cloud_off(p: psutil.Process) -> bool | None:
    try:
        return p.environ().get("OLLAMA_NO_CLOUD") == "1"
    except psutil.Error:
        return None  # cannot tell (another user's process)


def status() -> tuple[bool, str]:
    """(stays local, explanation) for the model server as it is running now."""
    apps, servers = _processes()
    if apps:
        return False, "the Ollama desktop app is running; it and its server contact external addresses"
    if not servers:
        return (False, "a model server answers on port 11434 but is not an Ollama process this user can see") if up() \
            else (False, "the model server is not running")
    states = [_cloud_off(s) for s in servers]
    if all(s is True for s in states):
        return True, "server running with cloud features switched off (OLLAMA_NO_CLOUD=1)"
    if any(s is None for s in states):
        return False, "cannot read the server's settings (it runs under another account)"
    return False, "the server is running with its cloud features on; it contacts an external address"


def ensure() -> str:
    """Make sure a local-only model server is running. Returns a line describing what was done."""
    ok, why = status()
    if ok and up():
        return "Model server: running, cloud features off"
    exe = ollama_exe()
    if not exe:
        return "Model server: Ollama is not installed. Run setup.bat. The UI will open, but tasks will fail."
    apps, servers = _processes()
    for p in apps + servers:  # the app would restart its own server, so it goes first
        try:
            p.kill()
        except psutil.Error:
            pass
    if apps or servers:
        time.sleep(2)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen([exe, "serve"], env={**os.environ, **ENV}, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, creationflags=flags)
    for _ in range(30):
        if up():
            note = " (the Ollama desktop app was stopped)" if apps else ""
            return f"Model server: started with cloud features off{note}"
        time.sleep(0.5)
    return "Model server: did not start. Run setup.bat, or check that Ollama is installed."
