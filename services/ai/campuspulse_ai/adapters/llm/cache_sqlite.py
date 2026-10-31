"""`SqliteCache`: the file-backed `ResponseCache` (offline `--use-llm` and local runs; P3.3).

stdlib `sqlite3` only. The online container uses `SupabaseCache` (`llm_calls.cache_key/response`)
instead; both store the raw model reply under the same sha256 key.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger(__name__)

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS llm_cache "
    "(key TEXT PRIMARY KEY, value TEXT NOT NULL, created_at TEXT NOT NULL)"
)


class SqliteCache:
    """Key/value cache in one SQLite file (implements `ResponseCache`).

    Creates the parent directory and the table on first use. Safe to share between threads (one
    connection behind a lock). A cache must never fail a request: a SQLite error is logged and `get`
    returns None / `put` does nothing.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        with self._lock, self._conn:
            self._conn.execute(_SCHEMA)

    def get(self, key: str) -> str | None:
        try:
            with self._lock:
                row = self._conn.execute("SELECT value FROM llm_cache WHERE key = ?", (key,)).fetchone()
        except sqlite3.Error as exc:
            log.warning("llm cache read failed: %s", exc)
            return None
        return None if row is None else str(row[0])

    def put(self, key: str, value: str) -> None:
        try:
            with self._lock, self._conn:
                self._conn.execute(
                    "INSERT OR REPLACE INTO llm_cache (key, value, created_at) VALUES (?, ?, ?)",
                    (key, value, datetime.now(UTC).isoformat()),
                )
        except sqlite3.Error as exc:
            log.warning("llm cache write failed: %s", exc)

    def close(self) -> None:
        with self._lock:
            self._conn.close()
