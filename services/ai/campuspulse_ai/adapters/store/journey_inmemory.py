"""InMemoryJourneyStore: the JourneyStore port over Python lists (tests, offline runs)."""

from __future__ import annotations

import dataclasses
import math
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from campuspulse_ai.adapters.store import codec
from campuspulse_ai.adapters.store.inmemory import InMemoryRepository
from campuspulse_ai.domain.journey import Contact, HintMatch, TicketActivity, TicketHint

OPEN_STATUSES = ("new", "in_progress")
MAX_K = 20  # like match_ticket_hints


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class InMemoryJourneyStore:
    """Behaves like `SupabaseJourneyStore` (tests/contracts/test_journey_store_contract.py).

    `repo` supplies the profiles (`contact_for_alias`) and the tickets (`claim_reminder`); without
    one there are no contacts and no reminder can be claimed.
    """

    def __init__(self, repo: InMemoryRepository | None = None) -> None:
        self._repo = repo
        self._activity: list[TicketActivity] = []
        self._hints: list[TicketHint] = []

    def add_activity(self, a: TicketActivity) -> TicketActivity:
        saved = dataclasses.replace(a, id=a.id or str(uuid.uuid4()))
        self._activity.append(saved)
        return saved

    def activity_for(self, ticket_id: str) -> list[TicketActivity]:
        rows = [(a.created_at, i, a) for i, a in enumerate(self._activity) if a.ticket_id == ticket_id]
        return [a for _, _, a in sorted(rows, key=lambda t: (t[0], t[1]))]

    def add_hint(self, h: TicketHint) -> TicketHint:
        saved = dataclasses.replace(
            h, id=h.id or str(uuid.uuid4()), created_at=h.created_at or datetime.now(UTC)
        )
        self._hints.append(saved)
        return saved

    def nearest_hints(self, embedding: Sequence[float], k: int, min_sim: float) -> list[HintMatch]:
        scored = [(_cosine(embedding, h.embedding), h) for h in self._hints if h.embedding is not None]
        scored = [(s, h) for s, h in scored if s >= min_sim]
        scored.sort(key=lambda t: (-t[0], -(t[1].created_at or datetime.min.replace(tzinfo=UTC)).timestamp()))
        limit = min(max(k, 0), MAX_K)
        return [
            HintMatch(
                hint_id=h.id,
                request_text=h.request_text,
                corrected_category=h.corrected_category,
                corrected_priority=h.corrected_priority,
                model_category=h.model_category,
                model_priority=h.model_priority,
                sim=s,
            )
            for s, h in scored[:limit]
        ]

    def contact_for_alias(self, alias: str) -> Contact | None:
        wanted = alias.strip()
        if self._repo is None or not wanted:
            return None
        for row in self._repo.tables["profiles"].values():
            if row.get("alias") == wanted:
                return Contact(
                    alias=wanted,
                    role=str(row.get("role") or "student"),
                    office=row.get("office") or None,
                    display_name=str(row.get("display_name") or ""),
                    demo_inbox=row.get("demo_inbox") or None,
                )
        return None

    def claim_reminder(self, ticket_id: str, level: int, now: datetime) -> bool:
        if self._repo is None:
            return False
        row = self._repo.tables["tickets"].get(ticket_id)
        if row is None or row.get("status") not in OPEN_STATUSES:
            return False
        if int(row.get("reminder_count") or 0) != level - 1:
            return False
        due = codec.parse_dt(row.get("sla_due_at"))
        if due is None or not due < now:
            return False
        row["reminder_count"] = level
        row["reminder_sent_at"] = codec.iso(now)
        return True
