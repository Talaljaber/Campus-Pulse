"""Routing table: category x priority -> ActionPlan (P3.8; SPEC §5.1 [11], UD-1).

Office and tech-team requests open tickets. Only Academic Support x high books an advisor slot
(and also opens a ticket); Registration x high is a same-day escalation ticket with no booking.

Pure and stdlib-only: `ActionsConfig.from_dict` validates the already-parsed `config/actions.yaml`
mapping (the YAML is read outside the domain, by the composition root or a test), and
`TableActionPlanner` implements the `ActionPlanner` port over it.

Plan rules, in order (ARCHITECTURE §2.1 [11]):
1. flag `safety` -> the `safety` rule (a safety alert plus a ticket) for any category, even when
   provisional: safety always fires immediately;
2. `provisional` (HUMAN_REVIEW) -> a ticket only; the cell's own kind is kept as tag
   `deferred:<kind>` so `ActUseCase.finalize` can fire it after staff confirm;
3. otherwise the cell of the table.
Evidence tags (e.g. `exam_now` -> `exam-in-progress`) are added when the evidence name is in
`flags`: the caller passes the fired evidence names together with the prediction flags.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from campuspulse_ai.domain.labels import CATEGORY_ORDER, PRIORITY_ORDER, Category, Priority
from campuspulse_ai.domain.values import ActionPlan, ActionType

SAFETY_FLAG = "safety"
DEFERRED_TAG_PREFIX = "deferred:"

# The incident detector decides merges; a table cell never routes to one.
_ROUTABLE_KINDS = frozenset(ActionType) - {ActionType.INCIDENT_MERGE}
_TOP_KEYS = frozenset({"version", "offices", "sla_hours", "safety", "provisional", "routes"})
_CATEGORY_KEYS = frozenset({"office"} | {str(p) for p in PRIORITY_ORDER})
_CELL_KEYS = frozenset({"kind", "office", "tags", "also_ticket", "evidence_tags"})
_SAFETY_KEYS = frozenset({"kind", "tags", "also_ticket"})
_PROVISIONAL_KEYS = frozenset({"tags"})


@dataclass(frozen=True, slots=True)
class Route:
    """One table cell: what to do for a category x priority."""

    kind: ActionType
    office: str
    tags: tuple[str, ...] = ()
    also_ticket: bool = False
    evidence_tags: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True, slots=True)
class SafetyRule:
    """What a `safety` flag turns any plan into (the office stays the category's)."""

    kind: ActionType
    tags: tuple[str, ...] = ()
    also_ticket: bool = True


@dataclass(frozen=True, slots=True)
class ActionsConfig:
    """The validated `config/actions.yaml`.

    - `offices`: the allowed office codes (D-005); every route must use one of them.
    - `sla_hours`: hours to `sla_due_at` per priority (SPEC §5.1 [11]: high 24, medium 72, low 336).
    - `routes`: one `Route` per (category, priority); all 18 cells are required.
    - `safety`: the rule for the `safety` flag. `provisional_tags`: added to every provisional plan.
    """

    offices: frozenset[str]
    sla_hours: Mapping[Priority, int]
    routes: Mapping[tuple[Category, Priority], Route]
    safety: SafetyRule
    provisional_tags: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ActionsConfig:
        """Validate a parsed `actions.yaml` mapping. Raises `ValueError` naming the bad key.

        Unknown keys are errors too, so a typo cannot silently drop a tag or an office.
        """
        _keys(data, _TOP_KEYS, "actions.yaml", required={"offices", "sla_hours", "safety", "routes"})
        offices = frozenset(_strings(data["offices"], "offices"))
        if not offices:
            raise ValueError("offices must list at least one office code")

        priorities = {str(p) for p in PRIORITY_ORDER}
        sla_raw = _mapping(data["sla_hours"], "sla_hours")
        _keys(sla_raw, priorities, "sla_hours", required=priorities)
        sla_hours = {p: _positive_int(sla_raw[str(p)], f"sla_hours.{p}") for p in PRIORITY_ORDER}

        safety_raw = _mapping(data["safety"], "safety")
        _keys(safety_raw, _SAFETY_KEYS, "safety", required={"kind"})
        safety = SafetyRule(
            kind=_kind(safety_raw["kind"], "safety.kind"),
            tags=_strings(safety_raw.get("tags", []), "safety.tags"),
            also_ticket=_bool(safety_raw.get("also_ticket", True), "safety.also_ticket"),
        )

        provisional_raw = _mapping(data.get("provisional", {}), "provisional")
        _keys(provisional_raw, _PROVISIONAL_KEYS, "provisional")
        provisional_tags = _strings(provisional_raw.get("tags", []), "provisional.tags")

        categories = {str(c) for c in CATEGORY_ORDER}
        routes_raw = _mapping(data["routes"], "routes")
        _keys(routes_raw, categories, "routes", required=categories)
        routes: dict[tuple[Category, Priority], Route] = {}
        for category in CATEGORY_ORDER:
            where = f"routes.{category}"
            cat_raw = _mapping(routes_raw[str(category)], where)
            _keys(cat_raw, _CATEGORY_KEYS, where, required=priorities)
            for priority in PRIORITY_ORDER:
                routes[(category, priority)] = _route(
                    _mapping(cat_raw[str(priority)], f"{where}.{priority}"),
                    cat_raw.get("office"),
                    offices,
                    f"{where}.{priority}",
                )
        return cls(
            offices=offices,
            sla_hours=MappingProxyType(sla_hours),
            routes=MappingProxyType(routes),
            safety=safety,
            provisional_tags=provisional_tags,
        )

    def route(self, category: Category, priority: Priority) -> Route:
        """The table cell for `category` x `priority`."""
        return self.routes[(category, priority)]


class TableActionPlanner:
    """`ActionPlanner` over `ActionsConfig` (pure; no I/O, no errors for valid labels).

    `plan` returns the `ActionPlan` for one decided request (rules in the module docstring):
    `office` is the cell's office code, `sla_hours` comes from the priority (high for a safety plan),
    and `tags` keep their config order with duplicates removed.
    """

    def __init__(self, config: ActionsConfig) -> None:
        self._config = config

    @property
    def config(self) -> ActionsConfig:
        return self._config

    def plan(
        self, category: Category, priority: Priority, flags: frozenset[str], provisional: bool
    ) -> ActionPlan:
        cfg = self._config
        cell = cfg.route(category, priority)
        evidence_tags = tuple(tag for name, tag in cell.evidence_tags.items() if name in flags)
        provisional_tags = cfg.provisional_tags if provisional else ()

        if SAFETY_FLAG in flags:
            return ActionPlan(
                kind=cfg.safety.kind,
                office=cell.office,
                sla_hours=cfg.sla_hours[Priority.HIGH],
                tags=_unique((*cfg.safety.tags, *cell.tags, *evidence_tags, *provisional_tags)),
                also_ticket=cfg.safety.also_ticket,
            )
        if provisional:
            deferred = () if cell.kind == ActionType.TICKET else (f"{DEFERRED_TAG_PREFIX}{cell.kind}",)
            return ActionPlan(
                kind=ActionType.TICKET,
                office=cell.office,
                sla_hours=cfg.sla_hours[priority],
                tags=_unique((*provisional_tags, *deferred, *cell.tags, *evidence_tags)),
                also_ticket=False,
            )
        return ActionPlan(
            kind=cell.kind,
            office=cell.office,
            sla_hours=cfg.sla_hours[priority],
            tags=_unique((*cell.tags, *evidence_tags)),
            also_ticket=cell.also_ticket,
        )


def deferred_kind(plan: ActionPlan) -> ActionType | None:
    """The kind a provisional plan deferred (`deferred:<kind>` tag), or None."""
    for tag in plan.tags:
        if tag.startswith(DEFERRED_TAG_PREFIX):
            return ActionType(tag.removeprefix(DEFERRED_TAG_PREFIX))
    return None


# --------------------------------------------------------------------------- validation helpers


def _route(raw: Mapping[str, object], category_office: object, offices: frozenset[str], where: str) -> Route:
    _keys(raw, _CELL_KEYS, where, required={"kind"})
    office_value = raw.get("office", category_office)
    if not isinstance(office_value, str) or office_value not in offices:
        raise ValueError(f"{where}: office {office_value!r} is not one of {sorted(offices)}")
    evidence_raw = _mapping(raw.get("evidence_tags", {}), f"{where}.evidence_tags")
    evidence_tags: dict[str, str] = {}
    for name, tag in evidence_raw.items():
        if not isinstance(tag, str) or not tag:
            raise ValueError(f"{where}.evidence_tags.{name} must be a non-empty string")
        evidence_tags[name] = tag
    return Route(
        kind=_kind(raw["kind"], f"{where}.kind"),
        office=office_value,
        tags=_strings(raw.get("tags", []), f"{where}.tags"),
        also_ticket=_bool(raw.get("also_ticket", False), f"{where}.also_ticket"),
        evidence_tags=MappingProxyType(evidence_tags),
    )


def _keys(
    raw: Mapping[str, object], allowed: Iterable[str], where: str, *, required: Iterable[str] = ()
) -> None:
    allowed_set = frozenset(allowed)
    unknown = sorted(set(raw) - allowed_set)
    if unknown:
        raise ValueError(f"{where}: unknown key(s) {unknown}; allowed {sorted(allowed_set)}")
    missing = sorted(set(required) - set(raw))
    if missing:
        raise ValueError(f"{where}: missing key(s) {missing}")


def _mapping(value: object, where: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(k, str) for k in value):
        raise ValueError(f"{where} must be a mapping with string keys")
    return value


def _strings(value: object, where: str) -> tuple[str, ...]:
    if not isinstance(value, list | tuple) or not all(isinstance(v, str) and v for v in value):
        raise ValueError(f"{where} must be a list of non-empty strings")
    return tuple(value)


def _bool(value: object, where: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{where} must be true or false")
    return value


def _positive_int(value: object, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{where} must be a positive integer")
    return value


def _kind(value: object, where: str) -> ActionType:
    if not isinstance(value, str) or value not in {str(k) for k in _ROUTABLE_KINDS}:
        raise ValueError(f"{where}: {value!r} is not one of {sorted(str(k) for k in _ROUTABLE_KINDS)}")
    return ActionType(str(value))


def _unique(tags: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(tags))
