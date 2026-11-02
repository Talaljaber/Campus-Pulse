"""Student-journey domain helpers (P9). Extended by later work packages."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

TICKET_NUMBER_LENGTH = 8
MAX_FILE_BYTES = 5 * 1024 * 1024
"""Largest ticket file (migration 0015 `size_bytes` check and bucket `file_size_limit`)."""


def ticket_number(ticket_id: str) -> str:
    """The short, human-readable ticket number: the first 8 hex characters of the id, upper case."""
    return ticket_id.replace("-", "")[:TICKET_NUMBER_LENGTH].upper()


@dataclass(frozen=True)
class Contact:
    """Who a ticket email is about: a requester or a staff member (demo identities only)."""

    alias: str
    role: str  # "student", "staff" or "admin"
    office: str | None = None
    display_name: str = ""
    demo_inbox: str | None = None


class ActivityKind(StrEnum):
    """`ticket_activity.kind` (migration 0013)."""

    CREATED = "created"
    COMMENT = "comment"
    NOTE = "note"
    STATUS = "status"
    FORWARD = "forward"
    PRIORITY = "priority"
    STUDENT_ACTION = "student_action"
    REMINDER = "reminder"


class Visibility(StrEnum):
    """`ticket_activity.visibility`: `internal` rows (notes, reminders) are never shown to the requester."""

    PUBLIC = "public"
    INTERNAL = "internal"


class StudentAction(StrEnum):
    """The three requester buttons (`POST /v1/tickets/{id}/student-action`)."""

    SOLVED = "solved"
    CLOSE = "close"
    KEEP_OPEN = "keep_open"


@dataclass(frozen=True)
class TicketActivity:
    """One row of a ticket's thread (`ticket_activity`). `id` is "" until the store saved it."""

    ticket_id: str
    kind: ActivityKind
    actor_role: str  # student, staff, admin or system
    created_at: datetime
    visibility: Visibility = Visibility.PUBLIC
    actor_alias: str | None = None
    actor_office: str | None = None
    body: str = ""
    from_status: str | None = None
    to_status: str | None = None
    from_office: str | None = None
    to_office: str | None = None
    from_priority: str | None = None
    to_priority: str | None = None
    id: str = ""


@dataclass(frozen=True)
class TicketFile:
    """One file on a ticket (`ticket_files`, migration 0015). `id` is "" until the store saved it.

    `storage_path` is generated (`tickets/<ticket_id>/<uuid4>.<ext>`); the original filename is never kept.
    """

    ticket_id: str
    uploader_role: str  # student, staff or admin
    visibility: Visibility
    storage_path: str
    mime: str
    size_bytes: int
    ext: str
    created_at: datetime
    uploader_alias: str | None = None
    activity_id: str | None = None
    id: str = ""


@dataclass(frozen=True)
class TicketHint:
    """A staff correction for the chat agent's retrieval (`ticket_hints`); the frozen model never reads it."""

    kind: str  # "forward" or "priority"
    request_text: str
    corrected_category: str
    corrected_priority: str
    ticket_id: str | None = None
    lang: str | None = None
    embedding: tuple[float, ...] | None = None
    model_category: str | None = None
    model_priority: str | None = None
    note: str | None = None
    author_alias: str | None = None
    author_role: str | None = None
    created_at: datetime | None = None
    id: str = ""


@dataclass(frozen=True)
class HintMatch:
    """One nearest hint: what staff corrected a similar request to, and how similar it is (cosine)."""

    hint_id: str
    request_text: str
    corrected_category: str
    corrected_priority: str
    model_category: str | None
    model_priority: str | None
    sim: float
