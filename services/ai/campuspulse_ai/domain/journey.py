"""Student-journey domain helpers (P9). Extended by later work packages."""

from __future__ import annotations

from dataclasses import dataclass

TICKET_NUMBER_LENGTH = 8


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
