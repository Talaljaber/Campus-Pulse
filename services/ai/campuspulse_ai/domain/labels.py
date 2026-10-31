"""Official label vocabularies. The only place label strings exist (ARCHITECTURE §1.3)."""

from __future__ import annotations

from enum import StrEnum


class Category(StrEnum):
    REGISTRATION = "Registration"
    IT_SUPPORT = "IT Support"
    FINANCE = "Finance"
    TRANSPORTATION = "Transportation"
    FACILITIES = "Facilities"
    ACADEMIC_SUPPORT = "Academic Support"


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @property
    def rank(self) -> int:
        """low=0, medium=1, high=2."""
        return PRIORITY_ORDER.index(self)

    def bump(self) -> Priority:
        """One level up, capped at high."""
        return PRIORITY_ORDER[min(self.rank + 1, len(PRIORITY_ORDER) - 1)]


# Fixed column order for every probability vector.
CATEGORY_ORDER: tuple[Category, ...] = (
    Category.REGISTRATION,
    Category.IT_SUPPORT,
    Category.FINANCE,
    Category.TRANSPORTATION,
    Category.FACILITIES,
    Category.ACADEMIC_SUPPORT,
)
PRIORITY_ORDER: tuple[Priority, ...] = (Priority.LOW, Priority.MEDIUM, Priority.HIGH)

CATEGORY_LABELS: tuple[str, ...] = tuple(c.value for c in CATEGORY_ORDER)
PRIORITY_LABELS: tuple[str, ...] = tuple(p.value for p in PRIORITY_ORDER)
