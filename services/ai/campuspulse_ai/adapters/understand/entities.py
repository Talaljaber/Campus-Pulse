"""Deterministic entity extraction and grounding checks (UD-10, P3.3a).

Used by `RuleBasedUnderstander` to fill `Entities`, and by the LLM output validator to reject entities
that are not in the request ("use only facts present in the text"). Patterns cover EN, Arabic and
Arabizi. Matching runs on a lightly normalised copy of the text (Eastern digits → ASCII, Arabic letter
variants unified), so the patterns below are written in that normalised form.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from campuspulse_ai.domain.values import Entities, NormalizedRequest

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_AR_LETTERS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي", "ـ": None})
_AR_DIACRITICS = re.compile("[ً-ْٰ]")
_ARABIC_LETTER = re.compile("[ء-ي]")
_LATIN_LETTER = re.compile("[A-Za-z]")

# A course code: 2-4 letters and a 3-digit number ("CS 201", "cs201", "MATH-101").
_COURSE = re.compile(r"\b([A-Za-z]{2,4})\s?-?\s?(\d{3})\b")
_NOT_COURSE_PREFIX = frozenset(
    {"room", "lab", "hall", "bldg", "gate", "floor", "bus", "line", "page", "ext", "tel"}
)
# A room code: one capital letter (the building) and a 3-digit number ("H 204", "M214").
_ROOM_CODE = re.compile(r"\b([A-Z])\s?-?\s?(\d{3})\b")
_ROOM_WORD = re.compile(
    r"(?:\b(?:room|lab|hall)\s*#?\s*|(?<!\w)[وفبل]?(?:ال)?(?:قاعه|غرفه|مختبر|لاب)\s*)(\d{2,4})\b",
    re.IGNORECASE,
)
_BUILDING = re.compile(
    r"\b(?i:building|bldg\.?)\s+([A-Z]{1,2})\b|\b([A-Z]{1,2})\s+(?i:building)\b|مبني\s*([A-Za-z]{1,2})\b"
)
_TODAY = re.compile(
    r"\b(?:today|tonight)\b|(?<!\w)[وفبل]?(?:اليوم|الليله)(?!\w)|\b[ei]l[ -]?yo?u?m\b",
    re.IGNORECASE,
)
_TOMORROW = re.compile(r"\btomorrow\b|(?<!\w)[وفبل]?(?:بكرا|بكره)(?!\w)|\bbo?u?kra\b", re.IGNORECASE)
# System or service named in the text -> its canonical lowercase name. First match wins.
_SYSTEMS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(pattern, re.IGNORECASE))
    for name, pattern in (
        (
            "registration portal",
            r"registration (?:portal|system|page|website|site)|(?:بوابه|نظام|صفحه|موقع) التسجيل",
        ),
        (
            "e-learning",
            r"\be-?learning\b|learning platform|\bmoodle\b"
            r"|منصه التعلم|(?<!\w)المنصه(?!\w)|التعليم الالكتروني",
        ),
        ("student portal", r"student portal|بوابه الطالب"),
        ("finance portal", r"finance portal|البوابه الماليه"),
        ("wifi", r"\bwi-?fi\b|\bwireless\b|الواي ?فاي|الانترنت|(?<!\w)النت(?!\w)"),
        ("university email", r"\be-?mail\b|الايميل"),
        ("university account", r"university account|account is locked|locked out|حسابي الجامعي|حساب الجامعه"),
        ("bus pass", r"bus pass|بطاقه الباص"),
    )
)


def ascii_digits(text: str) -> str:
    """Eastern-Arabic and Persian digits → ASCII."""
    return text.translate(_DIGITS)


def normalise(text: str) -> str:
    """The matching form: ASCII digits, unified Arabic letters, no diacritics or tatweel."""
    return _AR_DIACRITICS.sub("", ascii_digits(text).translate(_AR_LETTERS))


def compact(text: str) -> str:
    """`normalise` + lowercase, without spaces, hyphens or dots (for "is this value in the text?")."""
    return re.sub(r"[\s\-.]", "", normalise(text).lower())


def has_arabic(text: str) -> bool:
    return bool(_ARABIC_LETTER.search(text))


def has_latin(text: str) -> bool:
    return bool(_LATIN_LETTER.search(text))


def request_text(req: NormalizedRequest) -> str:
    """Everything the student wrote, in matching form: the wrapper-stripped original and the model text
    (normalised Arabic, or the Arabizi transliteration plus the original)."""
    return normalise(f"{req.core}\n{req.model_text}")


def grounded(value: str, req: NormalizedRequest) -> bool:
    """True when `value` occurs in the request text (case, spacing, hyphens and digit script ignored)."""
    needle = compact(value)
    return bool(needle) and needle in compact(f"{req.raw}\n{req.core}\n{req.model_text}")


def extract_entities(req: NormalizedRequest, today: date) -> Entities:
    """Rule-based entities. A picked or extracted `req.location` wins over the text for building/room."""
    text = request_text(req)
    course = None
    for m in _COURSE.finditer(text):
        if m.group(1).lower() not in _NOT_COURSE_PREFIX:
            course = f"{m.group(1).upper()} {m.group(2)}"
            break
    room = building = None
    if (code := _ROOM_CODE.search(text)) is not None:
        room, building = f"{code.group(1)} {code.group(2)}", code.group(1)
    elif (word := _ROOM_WORD.search(text)) is not None:
        room = word.group(1)
    if (b := _BUILDING.search(text)) is not None:
        building = next(g for g in b.groups() if g)
    if req.location is not None:
        building = req.location.building
        room = req.location.room or room
    deadline = None
    if _TODAY.search(text):
        deadline = today
    elif _TOMORROW.search(text):
        deadline = today + timedelta(days=1)
    system = next((name for name, pattern in _SYSTEMS if pattern.search(text)), None)
    return Entities(building=building, room=room, course_code=course, deadline=deadline, system=system)
