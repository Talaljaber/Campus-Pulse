"""UD-13 hybrid advisor routing: review assignment, the advisor's review list and forward, ticket forward.

Unit level over `build_test()` (InMemoryRepository, fakes) plus the HTTP routes over the real app
(trusted headers: the advisor is identified by alias -> profile id).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import pytest
from fixtures.api import api_client, auth
from fixtures.backend_fakes import FakeCore, make_core
from fixtures.containers import (
    ADVISOR_EMAIL,
    BackendTestContainer,
    build_test,
    link_student_advisor,
    load_yaml,
)
from fixtures.lifecycle import build_lifecycle

from campuspulse_ai.adapters.memory.inmemory import InMemoryMemoryStore
from campuspulse_ai.application.dto import FeedbackRequest, TriageRequest, TriageResponse
from campuspulse_ai.application.use_cases.feedback import FeedbackUseCase
from campuspulse_ai.application.use_cases.offices import OfficeMap
from campuspulse_ai.application.use_cases.reviews import (
    KIND_REVIEW_ASSIGNED,
    KIND_TICKET_FORWARDED,
    ReviewsUseCase,
)
from campuspulse_ai.application.use_cases.ticket_lifecycle import FORWARDED_TAG, TicketLifecycleUseCase
from campuspulse_ai.config.paths import CONFIG_DIR
from campuspulse_ai.domain.errors import InvalidInput, NotFound, Unauthorized
from campuspulse_ai.domain.labels import Category, Priority
from campuspulse_ai.domain.routing import ActionsConfig

UNSURE = "the portal is broken and I can't add my course"
URGENT = "the portal is broken and my registration closes today"
DANGER = "there is smoke in the lab and the course portal is down"
SAD = "I feel hopeless and can't go on"
STUDENT = "demo-17"
THREE = ["Registration", "IT Support", "Academic Support"]
P_THREE = {"Registration": 0.4, "IT Support": 0.35, "Academic Support": 0.25}


@dataclass(frozen=True)
class Who:
    role: str
    office: str | None = None
    alias: str | None = None
    user_id: str | None = None


ADMIN = Who("admin", alias="admin")
IT_STAFF = Who("staff", "it", "staff-it")
ACADEMIC_STAFF = Who("staff", "academic", "staff-academic")


class FakeEncoder:
    dim = 3
    model_id = "fake"

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.0, 1.0, 0.0] for _ in texts]


@dataclass
class H:
    c: BackendTestContainer
    advisor_profile: str
    memory: InMemoryMemoryStore
    feedback: FeedbackUseCase
    reviews: ReviewsUseCase
    forward: TicketLifecycleUseCase

    @property
    def advisor(self) -> Who:
        return Who("staff", "academic", "advisor", self.advisor_profile)

    def triage(self, text: str, alias: str = STUDENT) -> TriageResponse:
        return self.c.triage.run(TriageRequest(text=text, student_alias=alias))

    def review_of(self, r: TriageResponse) -> dict[str, Any]:
        pid = self.c.repo.latest_prediction(r.request_id).id
        [row] = [x for x in self.c.repo.tables["review_queue"].values() if x["prediction_id"] == pid]
        return row

    def notes(self, kind: str) -> list[dict[str, Any]]:
        return [n for n in self.c.notifications() if n["kind"] == kind]


def offices() -> OfficeMap:
    return OfficeMap.from_actions(ActionsConfig.from_dict(load_yaml(CONFIG_DIR / "actions.yaml")))


@pytest.fixture
def h() -> H:
    core = (
        FakeCore()
        .add(UNSURE, make_core(P_THREE, {"medium": 0.9}, set_cat=THREE))
        .add(URGENT, make_core(P_THREE, {"high": 0.9}, set_cat=THREE))
        .add(DANGER, make_core(P_THREE, {"medium": 0.9}, set_cat=THREE, safety=True))
        .add(SAD, make_core({"Academic Support": 0.9}, {"high": 0.9}, flags=frozenset({"distress"})))
    )  # fmt: skip
    c = build_test(core=core, record_sink=True)
    profile = link_student_advisor(c, STUDENT)
    memory = InMemoryMemoryStore()
    sinks = (c.sink,)
    feedback = FeedbackUseCase(c.repo, c.repo, memory, c.act, FakeEncoder(), c.clock, sinks, directory=c.repo)
    reviews = ReviewsUseCase(c.repo, c.repo, feedback, offices(), c.repo, c.repo, c.messages, limit=50)
    forward = build_lifecycle(c).lifecycle
    return H(c, profile, memory, feedback, reviews, forward)


# --------------------------------------------------------------------------- routing


def test_an_unsure_request_goes_to_the_students_advisor(h: H) -> None:
    r = h.triage(UNSURE)
    assert r.status == "human_review" and r.action is not None and r.action.provisional
    review = h.review_of(r)
    assert (review["assignee"], review["office"], review["reason"]) == (
        h.advisor_profile,
        "academic",
        "needs_review",
    )
    [note] = h.notes(KIND_REVIEW_ASSIGNED)
    assert note["alias"] == "advisor" and note["payload"]["review_id"] == review["id"]
    assert note["payload"]["assigned"] is True and STUDENT in note["payload"]["message"]
    [email] = [m for m in h.c.outbox() if m["to_address"] == ADVISOR_EMAIL]
    assert email["status"] == "sent" and "review" in email["subject"].lower()
    [event] = h.c.events("review.assigned")
    assert event["payload"]["assignee"] == h.advisor_profile and event["payload"]["urgent"] is False


def test_without_an_advisor_the_item_waits_in_the_academic_queue(h: H) -> None:
    r = h.triage(UNSURE, alias="demo-99")
    review = h.review_of(r)
    assert (review["assignee"], review["office"]) == (None, "academic")
    [note] = h.notes(KIND_REVIEW_ASSIGNED)
    assert note["alias"] == "office:academic" and note["payload"]["assigned"] is False
    assert not [m for m in h.c.outbox() if m["to_address"] == ADVISOR_EMAIL]


def test_a_same_day_request_never_waits_for_the_advisor(h: H) -> None:
    r = h.triage(URGENT)
    assert r.status == "human_review" and r.action is not None and r.action.ticket_id
    review = h.review_of(r)
    assert (review["assignee"], review["office"]) == (None, "registrar")  # the predicted office acts now
    ticket = h.c.repo.get_ticket(r.action.ticket_id)
    assert ticket.office == "registrar" and ticket.priority == Priority.HIGH
    assert h.notes(KIND_REVIEW_ASSIGNED)[0]["alias"] == "office:registrar"
    assert h.c.events("review.assigned")[0]["payload"]["urgent"] is True


def test_a_safety_request_alerts_at_once_and_stays_with_the_office(h: H) -> None:
    r = h.triage(DANGER)
    assert r.action is not None and r.action.type == "safety_alert" and "safety" in r.flags
    assert h.c.events("act.safety_alert")
    review = h.review_of(r)
    assert review["assignee"] is None and review["office"] == "registrar"


def test_distress_stays_admin_only_and_unassigned(h: H) -> None:
    r = h.triage(SAD)
    assert r.status == "distress"
    review = h.review_of(r)
    assert review["reason"] == "distress" and review["assignee"] is None
    assert not h.notes(KIND_REVIEW_ASSIGNED)
    assert [i.reason for i in h.reviews.queue(ADMIN)] == ["distress"]
    assert h.reviews.queue(h.advisor) == [] and h.reviews.queue(ACADEMIC_STAFF) == []


# --------------------------------------------------------------------------- list


def test_each_reviewer_sees_only_their_queue(h: H) -> None:
    mine = h.triage(UNSURE)
    queued = h.triage(UNSURE, alias="demo-99")
    other_profile = h.c.repo.add_profile("advisor-2", "staff", "academic")
    theirs = h.triage(UNSURE, alias="demo-50")
    h.c.repo.tables["review_queue"][h.review_of(theirs)["id"]]["assignee"] = other_profile

    advisor_view = h.reviews.queue(h.advisor)
    assert {i.request_id for i in advisor_view} == {mine.request_id, queued.request_id}
    [own] = [i for i in advisor_view if i.assigned_to_me]
    assert own.request_id == mine.request_id and own.student_alias == STUDENT and own.text == UNSURE
    assert own.set_cat == [Category.REGISTRATION, Category.IT_SUPPORT, Category.ACADEMIC_SUPPORT]
    assert own.ticket_id == mine.action.ticket_id if mine.action else False
    assert {i.request_id for i in h.reviews.queue(ACADEMIC_STAFF)} == {queued.request_id}
    assert h.reviews.queue(IT_STAFF) == []
    assert len(h.reviews.queue(ADMIN)) == 3
    with pytest.raises(Unauthorized):
        h.reviews.queue(Who("student", alias=STUDENT))


# --------------------------------------------------------------------------- review forward


def test_the_advisor_forwards_to_it_and_the_model_learns(h: H) -> None:
    r = h.triage(UNSURE)
    review_id = h.review_of(r)["id"]
    out = h.reviews.forward(review_id, "it", h.advisor, "platform outage")
    assert (out.category, out.tier, out.message.startswith("Corrected")) == (
        Category.IT_SUPPORT,
        "human",
        True,
    )
    assert out.ticket is not None and (out.ticket.office, out.ticket.provisional) == ("it", False)
    review = h.c.repo.get_review(review_id)
    assert (review.status, review.corrected_category, review.note) == (
        "corrected",
        Category.IT_SUPPORT,
        "platform outage",
    )
    [example] = h.memory.active()
    assert example.category == Category.IT_SUPPORT and out.memory.example_id == example.id
    [note] = h.notes(KIND_TICKET_FORWARDED)
    assert note["alias"] == "office:it" and note["payload"]["from_office"] == "academic"
    assert ("update_status", out.ticket.id) in h.c.sink.calls
    assert h.c.events("review.forwarded")[0]["payload"]["to_office"] == "it"
    assert h.reviews.queue(h.advisor) == []  # resolved items leave the open list


def test_forwarding_to_the_predicted_office_is_a_confirmation(h: H) -> None:
    r = h.triage(UNSURE)
    out = h.reviews.forward(h.review_of(r)["id"], "registrar", h.advisor)
    assert out.category == Category.REGISTRATION and out.message.startswith("Confirmed")
    assert h.c.events("feedback.confirmed") and not h.c.events("feedback.corrected")


def test_forward_errors(h: H) -> None:
    r = h.triage(UNSURE)
    review_id = h.review_of(r)["id"]
    with pytest.raises(Unauthorized):
        h.reviews.forward(review_id, "it", ACADEMIC_STAFF)  # assigned to the advisor, not to them
    with pytest.raises(Unauthorized):
        h.reviews.forward(review_id, "it", IT_STAFF)
    with pytest.raises(InvalidInput):
        h.reviews.forward(review_id, "library", h.advisor)
    with pytest.raises(NotFound):
        h.reviews.forward("00000000-0000-4000-8000-000000000000", "it", h.advisor)
    h.reviews.forward(review_id, "it", ADMIN)
    with pytest.raises(InvalidInput):
        h.reviews.forward(review_id, "finance", ADMIN)  # already resolved
    sad = h.review_of(h.triage(SAD))["id"]
    with pytest.raises(InvalidInput):
        h.reviews.forward(sad, "academic", ADMIN)


def test_feedback_respects_the_assignment(h: H) -> None:
    r = h.triage(UNSURE)
    pid = h.c.repo.latest_prediction(r.request_id).id
    with pytest.raises(Unauthorized):
        h.feedback.run(FeedbackRequest(prediction_id=pid), ACADEMIC_STAFF)
    out = h.feedback.run(FeedbackRequest(prediction_id=pid, corrected_priority=Priority.LOW), h.advisor)
    assert out.priority == Priority.LOW


# --------------------------------------------------------------------------- ticket forward


def test_staff_forward_a_ticket_to_another_office(h: H) -> None:
    r = h.triage(URGENT)
    assert r.action is not None and r.action.ticket_id
    tid = r.action.ticket_id
    registrar = Who("staff", "registrar", "staff-registrar")
    fwd = h.forward.forward(tid, registrar, " it ", "portal outage, not a registration problem")
    assert (fwd.ticket.office, fwd.ticket.category, fwd.from_office) == (
        "it",
        Category.IT_SUPPORT,
        "registrar",
    )
    saved = h.c.repo.get_ticket(tid)
    assert saved.office == "it" and FORWARDED_TAG in saved.tags and saved.priority == Priority.HIGH
    assert saved.title.startswith("IT Support/high: ")  # the rule title's stale label prefix is replaced
    [event] = h.c.events("ticket.forwarded")
    assert event["payload"] == {
        "by": "staff-registrar",
        "role": "staff",
        "from": "registrar",
        "to": "it",
        "note": "portal outage, not a registration problem",
    }
    h.forward.deliver(fwd)
    assert h.c.sink.calls[-1] == ("update_status", tid)
    [note] = h.notes(KIND_TICKET_FORWARDED)
    assert note["alias"] == "office:it" and "registrar" in note["payload"]["message"]


def test_ticket_forward_errors(h: H) -> None:
    r = h.triage(URGENT)
    assert r.action is not None and r.action.ticket_id
    tid = r.action.ticket_id
    with pytest.raises(Unauthorized):
        h.forward.forward(tid, IT_STAFF, "it")  # not the ticket's office
    with pytest.raises(InvalidInput):
        h.forward.forward(tid, ADMIN, "registrar")  # already there
    with pytest.raises(InvalidInput):
        h.forward.forward(tid, ADMIN, "library")
    with pytest.raises(NotFound):
        h.forward.forward("00000000-0000-4000-8000-000000000000", ADMIN, "it")


def test_office_map_is_one_to_one() -> None:
    m = offices()
    assert m.category_for("it") == Category.IT_SUPPORT and m.office_for(Category.FACILITIES) == "facilities"
    assert len(m.offices) == 6
    raw = load_yaml(CONFIG_DIR / "actions.yaml")
    raw["routes"]["Finance"]["office"] = "registrar"
    with pytest.raises(ValueError, match="share one office"):
        OfficeMap.from_actions(ActionsConfig.from_dict(raw))
    raw = load_yaml(CONFIG_DIR / "actions.yaml")
    raw["routes"]["Finance"]["high"]["office"] = "registrar"
    with pytest.raises(ValueError, match="several offices"):
        OfficeMap.from_actions(ActionsConfig.from_dict(raw))


# --------------------------------------------------------------------------- HTTP


def test_routes_over_http(h: H) -> None:
    r = h.triage(UNSURE)
    client = api_client(h.c, feedback=h.feedback, reviews=h.reviews, lifecycle=h.forward)
    as_advisor = auth("staff", "advisor", "academic")

    listed = client.get("/v1/reviews", headers=as_advisor)
    assert listed.status_code == 200
    [item] = listed.json()
    assert item["assigned_to_me"] is True and item["request_id"] == r.request_id

    wrong = client.post(f"/v1/reviews/{item['id']}/forward", json={"office": "it"},
                        headers=auth("staff", "staff-academic", "academic"))  # fmt: skip
    assert wrong.status_code == 403 and wrong.json()["error"]["code"] == "forbidden"
    bad = client.post(f"/v1/reviews/{item['id']}/forward", json={"office": "nope"}, headers=as_advisor)
    assert bad.status_code == 422

    done = client.post(
        f"/v1/reviews/{item['id']}/forward", json={"office": "it", "note": "x"}, headers=as_advisor
    )
    assert done.status_code == 200 and done.json()["ticket"]["office"] == "it"

    tid = done.json()["ticket"]["id"]
    moved = client.post(f"/v1/tickets/{tid}/forward", json={"office": "facilities"},
                        headers=auth("staff", "staff-it", "it"))  # fmt: skip
    assert moved.status_code == 200 and moved.json()["office"] == "facilities"
    assert [
        n for n in h.notes(KIND_TICKET_FORWARDED) if n["alias"] == "office:facilities"
    ]  # background task ran
    student = client.get("/v1/reviews", headers=auth("student", STUDENT))
    assert student.status_code == 403


def test_routes_answer_501_when_not_wired(h: H) -> None:
    client = api_client(h.c)
    assert client.get("/v1/reviews", headers=auth("admin")).status_code == 501
    assert (
        client.post("/v1/tickets/x/forward", json={"office": "it"}, headers=auth("admin")).status_code == 501
    )
