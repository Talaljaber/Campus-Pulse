"""P3.12: the clarification round trip over HTTP, and its error mapping (docs/api/README.md › Errors)."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from fixtures.api import api_client, auth
from fixtures.backend_fakes import FakeCore, make_core
from fixtures.containers import build_test

TEXT = "my registration page is broken"
REG_OR_IT = make_core(
    {"Registration": 0.55, "IT Support": 0.4}, {"medium": 0.9}, set_cat=["Registration", "IT Support"]
)
STUDENT = auth("student", "demo-17")


def ask() -> tuple[TestClient, dict[str, Any]]:
    client = api_client(build_test(core=FakeCore().add(TEXT, REG_OR_IT)))
    r = client.post("/v1/triage", json={"text": TEXT}, headers=STUDENT)
    assert r.status_code == 200
    body: dict[str, Any] = r.json()
    return client, body


def clarify(client: TestClient, request_id: str, headers: dict[str, str], **answer: str) -> Any:
    return client.post(f"/v1/triage/{request_id}/clarify", json=answer, headers=headers)


def test_ambiguous_request_asks_then_the_answer_decides_registration() -> None:
    client, first = ask()
    assert first["status"] == "needs_clarification"
    question = first["clarification"]
    assert len(question["options"]) >= 2
    r = clarify(
        client, first["request_id"], STUDENT, question_id=question["question_id"], option_id="registration"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["status"], body["category"]["label"]) == ("decided", "Registration")
    assert body["explanation"]["trace"]["policy_path"] == ["d_ask", "c_accept"]
    assert body["explanation"]["trace"]["clarified"] is True


def test_wrong_question_id_is_422_and_a_second_answer_is_409() -> None:
    client, first = ask()
    rid, qid = first["request_id"], first["clarification"]["question_id"]
    wrong = clarify(client, rid, STUDENT, question_id="pri:deadline", option_id="yes_today")
    assert wrong.status_code == 422 and wrong.json()["error"]["code"] == "invalid_input"
    assert clarify(client, rid, STUDENT, question_id=qid, option_id="it").status_code == 200
    again = clarify(client, rid, STUDENT, question_id=qid, option_id="it")
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "clarification_budget_exceeded"


def test_unknown_request_or_option_is_404() -> None:
    client, first = ask()
    qid = first["clarification"]["question_id"]
    missing = clarify(
        client, "00000000-0000-0000-0000-000000000000", STUDENT, question_id=qid, option_id="it"
    )
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "not_found"
    bad_option = clarify(client, first["request_id"], STUDENT, question_id=qid, option_id="nope")
    assert bad_option.status_code == 404


def test_body_must_carry_exactly_one_answer() -> None:
    client, first = ask()
    r = clarify(client, first["request_id"], STUDENT, question_id="x")
    assert r.status_code == 422 and r.json()["error"]["details"]["errors"]


def test_a_student_cannot_answer_another_students_question() -> None:
    client, first = ask()
    qid = first["clarification"]["question_id"]
    r = clarify(client, first["request_id"], auth("student", "demo-99"), question_id=qid, option_id="it")
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"


def test_staff_may_not_clarify() -> None:
    client, first = ask()
    qid = first["clarification"]["question_id"]
    r = clarify(client, first["request_id"], auth("staff", office="it"), question_id=qid, option_id="it")
    assert r.status_code == 403
