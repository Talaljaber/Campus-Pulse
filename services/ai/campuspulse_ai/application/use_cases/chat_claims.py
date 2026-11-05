"""Durable idempotency contract for confirmed chat proposals."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from campuspulse_ai.application import dto

ClaimStatus = Literal["claimed", "in_progress", "completed", "invalid"]


@dataclass(frozen=True)
class ConfirmationClaim:
    status: ClaimStatus
    request_id: str
    result: dto.ChatConfirmResponse | None = None


class ChatClaimStore(Protocol):
    def claim(self, digest: str, alias: str, request_id: str, expires_at: datetime) -> ConfirmationClaim: ...

    def complete(self, digest: str, result: dto.ChatConfirmResponse) -> bool: ...


class InMemoryChatClaimStore:
    def __init__(self) -> None:
        self._rows: dict[str, tuple[str, str, dto.ChatConfirmResponse | None]] = {}
        self._lock = threading.Lock()

    def claim(self, digest: str, alias: str, request_id: str, expires_at: datetime) -> ConfirmationClaim:
        del expires_at
        with self._lock:
            row = self._rows.get(digest)
            if row is None:
                self._rows[digest] = (alias, request_id, None)
                return ConfirmationClaim("claimed", request_id)
            old_alias, old_id, result = row
            if old_alias != alias or old_id != request_id:
                return ConfirmationClaim("invalid", old_id)
            return ConfirmationClaim("completed" if result else "in_progress", old_id, result)

    def complete(self, digest: str, result: dto.ChatConfirmResponse) -> bool:
        with self._lock:
            row = self._rows.get(digest)
            if row is None or row[2] is not None:
                return False
            self._rows[digest] = (row[0], row[1], result)
            return True
