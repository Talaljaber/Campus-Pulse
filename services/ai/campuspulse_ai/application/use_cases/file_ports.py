"""Ports of the ticket files (P9.10): the file rows and the private blob storage.

`FileStore`: `adapters/store/files_inmemory.InMemoryFileStore` and `files_supabase.SupabaseFileStore`
(service role). `BlobStore`: `adapters/store/storage_supabase.SupabaseBlobStore` (Supabase Storage REST).
Errors: `StoreError`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from campuspulse_ai.domain.journey import TicketFile


@runtime_checkable
class FileStore(Protocol):
    def add_file(self, f: TicketFile) -> TicketFile:
        """Insert one row; the returned copy carries the id."""
        ...

    def get_file(self, file_id: str) -> TicketFile | None: ...

    def files_for_ticket(self, ticket_id: str) -> list[TicketFile]:
        """The ticket's files, oldest first."""
        ...

    def attach(self, file_ids: Sequence[str], activity_id: str) -> None:
        """Set `activity_id` on these (still unattached) files."""
        ...


@runtime_checkable
class BlobStore(Protocol):
    def put(self, path: str, data: bytes, mime: str) -> None:
        """Store the bytes under `path` in the private bucket (never overwrites)."""
        ...

    def sign(self, path: str, expires_in: int, download_as: str | None = None) -> str:
        """A link that works for `expires_in` seconds. `download_as` forces a download with that name."""
        ...
