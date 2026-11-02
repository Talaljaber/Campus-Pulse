"""In-memory `FileStore` and `BlobStore` (tests, offline runs)."""

from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Sequence

from campuspulse_ai.domain.errors import StoreError
from campuspulse_ai.domain.journey import TicketFile


class InMemoryFileStore:
    def __init__(self) -> None:
        self._files: list[TicketFile] = []

    def add_file(self, f: TicketFile) -> TicketFile:
        saved = dataclasses.replace(f, id=f.id or str(uuid.uuid4()))
        self._files.append(saved)
        return saved

    def get_file(self, file_id: str) -> TicketFile | None:
        return next((f for f in self._files if f.id == file_id), None)

    def files_for_ticket(self, ticket_id: str) -> list[TicketFile]:
        rows = [(f.created_at, i, f) for i, f in enumerate(self._files) if f.ticket_id == ticket_id]
        return [f for _, _, f in sorted(rows, key=lambda t: (t[0], t[1]))]

    def attach(self, file_ids: Sequence[str], activity_id: str) -> None:
        wanted = set(file_ids)
        self._files = [
            dataclasses.replace(f, activity_id=activity_id) if f.id in wanted and f.activity_id is None else f
            for f in self._files
        ]


class InMemoryBlobStore:
    """Keeps bytes in a dict; `sign` returns a fake link and records the expiry in `signed`."""

    def __init__(self) -> None:
        self.blobs: dict[str, tuple[bytes, str]] = {}
        self.signed: list[tuple[str, int, str | None]] = []

    def put(self, path: str, data: bytes, mime: str) -> None:
        if path in self.blobs:
            raise StoreError("storage upload failed: the object exists")
        self.blobs[path] = (data, mime)

    def sign(self, path: str, expires_in: int, download_as: str | None = None) -> str:
        if path not in self.blobs:
            raise StoreError("storage sign failed: no such object")
        self.signed.append((path, expires_in, download_as))
        return f"https://storage.invalid/sign/{path}?expires_in={expires_in}"
