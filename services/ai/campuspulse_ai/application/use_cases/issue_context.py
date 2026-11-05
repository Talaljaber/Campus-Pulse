"""Structured issue preparation before conversational classification."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from campuspulse_ai.application.use_cases.chat_ports import Turn


@dataclass(frozen=True)
class OpenTicket:
    """One of the requester's own open tickets, shown to the preparer so it can spot a repeat."""

    number: str
    text: str
    priority: str
    status: str


@dataclass(frozen=True)
class PreparedIssue:
    classifier_text: str
    priority_recommendation: str | None
    priority_evidence: tuple[str, ...]
    duplicate_of: str | None = None
    """The `number` of the open ticket this message is about (a repeat, or a follow-up adding detail)."""


class IssueContextPreparer(Protocol):
    def prepare(
        self, messages: Sequence[Turn], anchor: str, open_tickets: Sequence[OpenTicket] = ()
    ) -> PreparedIssue | None: ...
