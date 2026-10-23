"""Append-only JSONL audit trail of every agent event."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path


class Audit:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def log(self, session: str, event: dict) -> None:
        line = json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "session": session, **event})
        with self._lock, self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def tail(self, n: int = 100) -> list[dict]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()[-n:]
        return [json.loads(line) for line in lines]
