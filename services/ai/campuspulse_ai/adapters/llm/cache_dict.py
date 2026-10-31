"""`DictCache`: the in-process `ResponseCache` (tests, `build_test()`)."""

from __future__ import annotations

import threading


class DictCache:
    """A dict behind a lock (implements `ResponseCache`). `data` is exposed for test assertions."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.data: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        with self._lock:
            return self.data.get(key)

    def put(self, key: str, value: str) -> None:
        with self._lock:
            self.data[key] = value
