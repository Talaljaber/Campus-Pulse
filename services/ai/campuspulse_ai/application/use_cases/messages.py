"""Student-facing and notification texts for the use cases (`config/templates/messages.yaml`).

Pure: `Messages.from_dict` validates the already-parsed YAML mapping (the composition root or a test
reads the file). Unknown or missing keys raise `ValueError`, so a typo cannot silently drop a text.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, TypeVar

from campuspulse_ai.domain.values import Lang


@dataclass(frozen=True, slots=True)
class StudentMessages:
    """Texts the student sees, in one language (str.format placeholders in braces)."""

    distress: str
    out_of_scope: str
    human_review: str  # {category}
    ticket_opened: str  # {category}
    faq_source: str  # {source}
    demo_marker: str
    faq_unsure: str
    booking_confirmed: str  # {advisor} {starts_at}
    booking_unavailable: str
    safety: str  # {office}
    update_subject: str
    incident_merged: str  # {building} {reports}
    incident_resolved: str  # {title}


@dataclass(frozen=True, slots=True)
class EmailTemplates:
    """Emails to allow-listed demo inboxes (advisor, office, the student's demo inbox), in English."""

    booking_subject: str  # {title}
    booking_body: str  # {advisor} {starts_at} {ends_at} {ticket_id} {text}
    safety_subject: str  # {category} {building}
    safety_body: str  # {building} {ticket_id} {text}
    transport_subject: str  # {title}
    transport_body: str  # {ticket_id} {text}
    resolved_subject: str  # {title}
    resolved_body: str  # {title} {ticket_id} {note}
    review_subject: str  # {category} {priority}
    review_body: str  # {alias} {category} {priority} {text}


@dataclass(frozen=True, slots=True)
class StaffMessages:
    """In-app notes for office staff and advisors (P4.9, UD-13), in English."""

    escalated: str  # {old} {new} {sla_due_at}
    review_assigned: str  # {alias} {category} {priority}
    review_queued: str  # {category} {priority}
    ticket_forwarded: str  # {title} {from_office} {note}


T = TypeVar("T")

_TOP_KEYS = frozenset({"version", "student", "email", "staff"})
_LANG_KEYS = frozenset({"en", "ar"})


@dataclass(frozen=True, slots=True)
class Messages:
    """All texts: `student` per language (Arabizi reads the Arabic texts), `email` and `staff`."""

    en: StudentMessages
    ar: StudentMessages
    email: EmailTemplates
    staff: StaffMessages

    def for_lang(self, lang: Lang) -> StudentMessages:
        """The student texts for `lang`; Arabic script for `ar` and `arabizi` (UD-10 reply rule)."""
        return self.en if lang == Lang.EN else self.ar

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> Messages:
        """Validate a parsed `messages.yaml`. Raises `ValueError` naming the bad key."""
        _keys(data, _TOP_KEYS, "messages.yaml", required={"student", "email", "staff"})
        student = _mapping(data["student"], "student")
        _keys(student, _LANG_KEYS, "student", required=_LANG_KEYS)
        return cls(
            en=_build(StudentMessages, _mapping(student["en"], "student.en"), "student.en"),
            ar=_build(StudentMessages, _mapping(student["ar"], "student.ar"), "student.ar"),
            email=_build(EmailTemplates, _mapping(data["email"], "email"), "email"),
            staff=_build(StaffMessages, _mapping(data["staff"], "staff"), "staff"),
        )


def _build(cls: type[T], raw: Mapping[str, object], where: str) -> T:
    fields: tuple[Any, ...] = dataclasses.fields(cls)  # type: ignore[arg-type]
    names = frozenset(f.name for f in fields)
    _keys(raw, names, where, required=names)
    values: dict[str, str] = {}
    for name in names:
        value = raw[name]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{where}.{name} must be a non-empty string")
        values[name] = value.strip()
    return cls(**values)


def _keys(
    raw: Mapping[str, object], allowed: frozenset[str], where: str, *, required: frozenset[str] | set[str]
) -> None:
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ValueError(f"{where}: unknown key(s) {unknown}")
    missing = sorted(set(required) - set(raw))
    if missing:
        raise ValueError(f"{where}: missing key(s) {missing}")


def _mapping(value: object, where: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(k, str) for k in value):
        raise ValueError(f"{where} must be a mapping with string keys")
    return value
