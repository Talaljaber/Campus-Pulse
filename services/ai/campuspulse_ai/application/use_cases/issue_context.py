"""Structured issue preparation before conversational classification."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from campuspulse_ai.application.use_cases.chat_ports import Turn


@dataclass(frozen=True)
class PreparedIssue:
    classifier_text: str
    priority_recommendation: str | None
    priority_evidence: tuple[str, ...]


class IssueContextPreparer(Protocol):
    def prepare(self, messages: Sequence[Turn], anchor: str) -> PreparedIssue | None: ...
