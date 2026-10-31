"""P3.8: config/actions.yaml and TableActionPlanner (SPEC §5.1 [11], UD-1, D-005)."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from campuspulse_ai.domain.labels import CATEGORY_ORDER, PRIORITY_ORDER, Category, Priority
from campuspulse_ai.domain.ports import ActionPlanner
from campuspulse_ai.domain.routing import ActionsConfig, TableActionPlanner, deferred_kind
from campuspulse_ai.domain.values import ActionType

ACTIONS_YAML = Path(__file__).resolve().parents[4] / "config" / "actions.yaml"
D005_OFFICES = {"registrar", "it", "finance", "transport", "facilities", "academic"}
A, R, IT, F, T, FA = (
    Category.ACADEMIC_SUPPORT,
    Category.REGISTRATION,
    Category.IT_SUPPORT,
    Category.FINANCE,
    Category.TRANSPORTATION,
    Category.FACILITIES,
)
LOW, MED, HIGH = Priority.LOW, Priority.MEDIUM, Priority.HIGH
FAQ, TICKET, BOOKING, ALERT = (
    ActionType.FAQ_ANSWER,
    ActionType.TICKET,
    ActionType.BOOKING,
    ActionType.SAFETY_ALERT,
)

# SPEC §5.1 [11] with UD-1: (kind, also_ticket) per cell.
EXPECTED: dict[tuple[Category, Priority], tuple[ActionType, bool]] = {
    (A, LOW): (FAQ, False), (A, MED): (TICKET, False), (A, HIGH): (BOOKING, True),
    (R, LOW): (FAQ, False), (R, MED): (TICKET, False), (R, HIGH): (TICKET, False),
    (IT, LOW): (FAQ, False), (IT, MED): (TICKET, False), (IT, HIGH): (TICKET, False),
    (F, LOW): (FAQ, False), (F, MED): (TICKET, False), (F, HIGH): (TICKET, False),
    (T, LOW): (FAQ, False), (T, MED): (TICKET, False), (T, HIGH): (TICKET, False),
    (FA, LOW): (TICKET, False), (FA, MED): (TICKET, False), (FA, HIGH): (ALERT, True),
}  # fmt: skip
OFFICE = {A: "academic", R: "registrar", IT: "it", F: "finance", T: "transport", FA: "facilities"}
NO_FLAGS: frozenset[str] = frozenset()


def raw_config() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(ACTIONS_YAML.read_text(encoding="utf-8"))
    return data


@pytest.fixture(scope="module")
def planner() -> TableActionPlanner:
    return TableActionPlanner(ActionsConfig.from_dict(raw_config()))


def test_planner_implements_the_port(planner: TableActionPlanner) -> None:
    assert isinstance(planner, ActionPlanner)


@pytest.mark.parametrize(("category", "priority"), list(EXPECTED), ids=lambda v: str(v))
def test_every_cell_maps_to_its_kind_and_office(
    planner: TableActionPlanner, category: Category, priority: Priority
) -> None:
    plan = planner.plan(category, priority, NO_FLAGS, provisional=False)
    assert (plan.kind, plan.also_ticket) == EXPECTED[(category, priority)]
    assert plan.office == OFFICE[category]


def test_table_covers_all_18_cells(planner: TableActionPlanner) -> None:
    cells = {(c, p) for c in CATEGORY_ORDER for p in PRIORITY_ORDER}
    assert set(planner.config.routes) == cells == set(EXPECTED)


def test_offices_are_exactly_the_d005_codes(planner: TableActionPlanner) -> None:
    assert planner.config.offices == D005_OFFICES
    assert {route.office for route in planner.config.routes.values()} == D005_OFFICES


def test_sla_hours(planner: TableActionPlanner) -> None:
    assert dict(planner.config.sla_hours) == {HIGH: 24, MED: 72, LOW: 336}
    for priority, hours in ((HIGH, 24), (MED, 72), (LOW, 336)):
        assert planner.plan(R, priority, NO_FLAGS, provisional=False).sla_hours == hours


def test_ud1_only_academic_support_high_books(planner: TableActionPlanner) -> None:
    bookings = [cell for cell in EXPECTED if planner.plan(*cell, NO_FLAGS, provisional=False).kind == BOOKING]
    assert bookings == [(A, HIGH)]
    registration_high = planner.plan(R, HIGH, NO_FLAGS, provisional=False)
    assert registration_high.kind == TICKET and "same-day-escalation" in registration_high.tags


def test_safety_flag_overrides_any_category(planner: TableActionPlanner) -> None:
    for category in CATEGORY_ORDER:
        plan = planner.plan(category, HIGH, frozenset({"safety"}), provisional=False)
        assert (plan.kind, plan.also_ticket, plan.office) == (ALERT, True, OFFICE[category])
        assert plan.sla_hours == 24 and plan.tags[0] == "safety"


def test_provisional_defers_booking_into_a_ticket(planner: TableActionPlanner) -> None:
    plan = planner.plan(A, HIGH, NO_FLAGS, provisional=True)
    assert (plan.kind, plan.also_ticket, plan.office) == (TICKET, False, "academic")
    assert plan.tags[:2] == ("unconfirmed", "deferred:booking")
    assert deferred_kind(plan) == BOOKING


def test_provisional_ticket_has_nothing_deferred(planner: TableActionPlanner) -> None:
    plan = planner.plan(F, MED, NO_FLAGS, provisional=True)
    assert plan.kind == TICKET and plan.tags == ("unconfirmed",) and deferred_kind(plan) is None


def test_safety_fires_even_when_provisional(planner: TableActionPlanner) -> None:
    plan = planner.plan(FA, HIGH, frozenset({"safety", "needs_review"}), provisional=True)
    assert plan.kind == ALERT and plan.also_ticket and "unconfirmed" in plan.tags
    assert deferred_kind(plan) is None


def test_exam_evidence_adds_the_exam_tag(planner: TableActionPlanner) -> None:
    assert planner.plan(IT, HIGH, frozenset({"exam_now"}), provisional=False).tags == ("exam-in-progress",)
    assert planner.plan(IT, HIGH, NO_FLAGS, provisional=False).tags == ()
    assert planner.plan(IT, MED, frozenset({"exam_now"}), provisional=False).tags == ()


def test_plan_ignores_unrelated_flags(planner: TableActionPlanner) -> None:
    flags = frozenset({"injection_attempt", "urgency_unsupported", "priority_gaming_suspected"})
    assert planner.plan(R, LOW, flags, provisional=False) == planner.plan(R, LOW, NO_FLAGS, provisional=False)


def _broken(edit: str) -> dict[str, Any]:
    data = copy.deepcopy(raw_config())
    if edit == "missing_cell":
        del data["routes"]["Finance"]["high"]
    elif edit == "unknown_office":
        data["routes"]["Finance"]["office"] = "bursar"
    elif edit == "unknown_kind":
        data["routes"]["Finance"]["high"]["kind"] = "phone_call"
    elif edit == "incident_merge":
        data["routes"]["Finance"]["high"]["kind"] = "incident_merge"
    elif edit == "typo_key":
        data["routes"]["Finance"]["high"]["also_tiket"] = True
    elif edit == "missing_category":
        del data["routes"]["Transportation"]
    elif edit == "bad_sla":
        data["sla_hours"]["low"] = 0
    elif edit == "missing_sla":
        del data["sla_hours"]["medium"]
    return data


@pytest.mark.parametrize(
    "edit",
    ["missing_cell", "unknown_office", "unknown_kind", "incident_merge", "typo_key", "missing_category",
     "bad_sla", "missing_sla"],
)  # fmt: skip
def test_invalid_config_is_rejected(edit: str) -> None:
    with pytest.raises(ValueError):
        ActionsConfig.from_dict(_broken(edit))
