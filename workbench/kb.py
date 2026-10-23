"""Local knowledge base: SQLite full-text search (BM25) over document chunks.

Everything is one file on disk. No embedding model and no external service.
"""
from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path

CHUNK = 700  # characters per chunk


def _chunks(text: str) -> list[str]:
    out, cur = [], ""
    for line in text.splitlines():
        if cur and len(cur) + len(line) > CHUNK:
            out.append(cur.strip())
            cur = ""
        cur += line + "\n"
        while len(cur) > CHUNK * 2:  # one very long line
            out.append(cur[:CHUNK])
            cur = cur[CHUNK:]
    if cur.strip():
        out.append(cur.strip())
    return out


class KnowledgeBase:
    def __init__(self, path: Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        # Porter stemming: "approval" finds "approved", "repair" finds "repairs".
        self._db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS passages "
                         "USING fts5(doc, page UNINDEXED, text, tokenize='porter unicode61')")
        # Databases made before stemming used a table named `chunks`; move its rows across once.
        if self._db.execute("SELECT 1 FROM sqlite_master WHERE name = 'chunks'").fetchone():
            self._db.execute("INSERT INTO passages SELECT doc, page, text FROM chunks")
            self._db.execute("DROP TABLE chunks")
            self._db.commit()

    def add(self, doc: str, pages: list[dict]) -> int:
        """Index a document from ingest.extract() pages. Replaces any earlier copy."""
        rows = [(doc, p["page"], c) for p in pages for c in _chunks(p["text"])]
        with self._lock:
            self._db.execute("DELETE FROM passages WHERE doc = ?", (doc,))
            self._db.executemany("INSERT INTO passages VALUES (?, ?, ?)", rows)
            self._db.commit()
        return len(rows)

    def remove(self, doc: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM passages WHERE doc = ?", (doc,))
            self._db.commit()

    def documents(self) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT doc, COUNT(*) FROM passages GROUP BY doc ORDER BY doc").fetchall()
        return [{"doc": d, "chunks": n} for d, n in rows]

    def search(self, query: str, k: int = 4) -> list[dict]:
        terms = [t for t in re.findall(r"\w+", query) if len(t) > 2]
        if not terms:
            return []
        match = " OR ".join(f'"{t}"' for t in terms)
        with self._lock:
            rows = self._db.execute(
                "SELECT doc, page, text FROM passages WHERE passages MATCH ? ORDER BY bm25(passages) LIMIT ?",
                (match, k),
            ).fetchall()
        return [{"doc": d, "page": p, "text": t} for d, p, t in rows]
