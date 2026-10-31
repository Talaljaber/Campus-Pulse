"""P3.12 / X3.1: `/v1/triage` over HTTP returns the exact SPEC §7 key set (+ LD-25 `understood_as` and
`message`, UD-10 `understanding`) for each of the five statuses, with valid types."""

from __future__ import annotations

from typing import Any

import pytest
from fixtures.api import api_client, auth
from fixtures.backend_fakes import FakeCore, make_core
from fixtures.containers import build_test

from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS
from campuspulse_ai.domain.values import FLAGS, Lang, Tier

TRIAGE_KEYS = {
    "request_id", "status", "lang", "is_arabizi", "understood_as", "category", "priority", "tier",
    "clarification", "explanation", "flags", "action", "message", "understanding",
}  # fmt: skip
CATEGORY_KEYS = {"label", "prob", "set"}
PRIORITY_KEYS = {"label", "prob", "set", "evidence"}
ACTION_KEYS = {
    "type", "ticket_id", "external", "sla_due_at", "message", "provisional", "tags", "booking", "faq",
    "incident_id",
}  # fmt: skip
EXPLANATION_KEYS = {"top_tokens", "neighbors", "counterfactual", "trace"}
UNDERSTANDING_KEYS = {
    "summary_en", "summary_ar", "entities", "student_reply", "ticket_title", "ticket_body", "source",
    "prompt_version",
}  # fmt: skip

TEXTS = {
    "decided": "wifi is down in the library",
    "needs_clarification": "my registration page is broken",
    "human_review": "something about my account",
    "out_of_scope": "asdf qwer",
    "distress": "i can't cope with anything anymore",
}
CORES = {
    "needs_clarification": make_core(
        {"Registration": 0.55, "IT Support": 0.4}, {"high": 0.9}, set_cat=["Registration", "IT Support"]
    ),
    "human_review": make_core(
        {"Registration": 0.4, "IT Support": 0.3, "Finance": 0.25},
        {"medium": 0.9},
        set_cat=["Registration", "IT Support", "Finance"],
    ),
    "out_of_scope": make_core(flags=frozenset({"gibberish"})),
    "distress": make_core({"Academic Support": 0.9}, {"high": 0.9}, flags=frozenset({"distress"})),
}
# Which keys are non-null per status (docs/api/README.md › status values).
FILLED = {
    "decided": {"category", "priority", "explanation", "action", "understanding"},
    "needs_clarification": {"category", "priority", "clarification"},
    "human_review": {"category", "priority", "explanation", "action", "understanding", "message"},
    "out_of_scope": {"clarification", "message"},
    "distress": {"message"},
}
OPTIONAL = {"category", "priority", "clarification", "explanation", "action", "understanding", "message"}


def post_triage(status: str) -> dict[str, Any]:
    core = FakeCore()
    for name, result in CORES.items():
        core.add(TEXTS[name], result)
    client = api_client(build_test(core=core))
    r = client.post("/v1/triage", json={"text": TEXTS[status]}, headers=auth("student", "demo-17"))
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    return body


def _prob(value: object) -> None:
    assert isinstance(value, float) and 0.0 <= value <= 1.0


@pytest.mark.parametrize("status", list(TEXTS))
def test_exact_key_set_and_types_per_status(status: str) -> None:
    body = post_triage(status)
    assert set(body) == TRIAGE_KEYS
    assert body["status"] == status
    assert body["lang"] in {lang.value for lang in Lang} and isinstance(body["is_arabizi"], bool)
    assert body["tier"] in {t.value for t in Tier}
    assert isinstance(body["flags"], list) and set(body["flags"]) <= FLAGS
    assert {k for k in OPTIONAL if body[k] is not None} == FILLED[status]
    if body["category"] is not None:
        assert set(body["category"]) == CATEGORY_KEYS and body["category"]["label"] in CATEGORY_LABELS
        _prob(body["category"]["prob"])
        assert set(body["category"]["set"]) <= set(CATEGORY_LABELS)
    if body["priority"] is not None:
        assert set(body["priority"]) == PRIORITY_KEYS and body["priority"]["label"] in PRIORITY_LABELS
        _prob(body["priority"]["prob"])
        assert set(body["priority"]["set"]) <= set(PRIORITY_LABELS)
    if body["action"] is not None:
        assert set(body["action"]) == ACTION_KEYS
    if body["explanation"] is not None:
        assert set(body["explanation"]) == EXPLANATION_KEYS
    if body["understanding"] is not None:
        assert set(body["understanding"]) == UNDERSTANDING_KEYS


def test_student_view_drops_staff_only_flags() -> None:
    """`urgency_unsupported` is staff-only; the student never sees it (`to_student_view`)."""
    text = "URGENT!!! where is the bus timetable"
    core = FakeCore().add(text, make_core({"Transportation": 0.9}, {"low": 0.9}), stated_urgency=True)
    client = api_client(build_test(core=core))
    staff = client.post("/v1/triage", json={"text": text}, headers=auth("staff", office="transport"))
    student = client.post("/v1/triage", json={"text": text}, headers=auth("student", "demo-17"))
    assert "urgency_unsupported" in staff.json()["flags"]
    assert "urgency_unsupported" not in student.json()["flags"]
