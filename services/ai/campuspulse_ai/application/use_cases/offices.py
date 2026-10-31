"""OfficeMap: the one-to-one category <-> office table of `config/actions.yaml` (D-005, UD-13).

Forwarding a request "to another office" is a category correction, because every category has exactly
one office (and every office one category). `OfficeMap.from_actions` checks that this still holds, so
a routing-table change that breaks it fails at startup instead of mislabelling a forward.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from campuspulse_ai.domain.errors import InvalidInput
from campuspulse_ai.domain.labels import CATEGORY_ORDER, PRIORITY_ORDER, Category
from campuspulse_ai.domain.routing import ActionsConfig


@dataclass(frozen=True, slots=True)
class OfficeMap:
    """`office_for(category)` and `category_for(office)` over the routing table.

    `category_for` raises `InvalidInput` (422) for a code that is not a routed office.
    """

    by_category: Mapping[Category, str]
    by_office: Mapping[str, Category]

    @classmethod
    def from_actions(cls, config: ActionsConfig) -> OfficeMap:
        """Build the map. Raises `ValueError` when a category routes to several offices (per priority)
        or two categories share one office: a forward would then be ambiguous."""
        by_category: dict[Category, str] = {}
        for category in CATEGORY_ORDER:
            offices = {config.route(category, priority).office for priority in PRIORITY_ORDER}
            if len(offices) != 1:
                raise ValueError(f"actions.yaml: {category} routes to several offices {sorted(offices)}")
            by_category[category] = offices.pop()
        by_office = {office: category for category, office in by_category.items()}
        if len(by_office) != len(by_category):
            raise ValueError("actions.yaml: two categories share one office, so forwards are ambiguous")
        return cls(by_category=MappingProxyType(by_category), by_office=MappingProxyType(by_office))

    @property
    def offices(self) -> tuple[str, ...]:
        """The routed office codes, in category order."""
        return tuple(self.by_category[c] for c in CATEGORY_ORDER)

    def office_for(self, category: Category) -> str:
        return self.by_category[category]

    def category_for(self, office: str) -> Category:
        code = office.strip()
        if code not in self.by_office:
            raise InvalidInput(f"unknown office {office!r}; expected one of {list(self.offices)}")
        return self.by_office[code]
