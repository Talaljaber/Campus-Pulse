"""P3.11 `FeedbackUseCase`: staff confirm or correct a prediction; the correction enters live memory."""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from dataclasses import dataclass

import pytest
from fixtures.backend_fakes import FakeCore, make_core
from fixtures.containers import BackendTestContainer, build_test

from campuspulse_ai.adapters.memory.inmemory import InMemoryMemoryStore
from campuspulse_ai.application.dto import FeedbackRequest, TriageRequest, TriageResponse
from campuspulse_ai.application.use_cases.feedback import FeedbackUseCase
from campuspulse_ai.application.use_cases.ports import FeedbackHandler
from campuspulse_ai.domain.errors import NotFound, Unauthorized
from campuspulse_ai.domain.labels import Category, Priority

AMBIGUOUS = "the portal is broken and I can't add my course"
CLEAR = "the shuttle bus is late again"
SAD = "I feel hopeless and can't go on"
STAFF_ID = "00000000-0000-4000-8000-0000000000aa"


@dataclass(frozen=True)
class Reviewer:
    role: str
    office: str | None = None
    alias: str | None = None
    user_id: str | None = STAFF_ID


STAFF = Reviewer("staff", "it", "staff-it")
ADMIN = Reviewer("admin", alias="admin")


class FakeEncoder:
    dim = 3
    model_id = "fake"

    def __init__(self) -> None:
        self.calls = 0

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        return [[0.0, 1.0, 0.0] for _ in texts]


@dataclass
class Harness:
    c: BackendTestContainer
    memory: InMemoryMemoryStore
    encoder: FakeEncoder
    feedback: FeedbackUseCase

    def triage(self, text: str) -> TriageResponse:
        return self.c.triage.run(TriageRequest(text=text, student_alias="demo-17"))

    def prediction_id(self, request_id: str) -> str:
        return self.c.repo.latest_prediction(request_id).id


@pytest.fixture
def h() -> Harness:
    three = ["Registration", "IT Support", "Academic Support"]
    p_three = {"Registration": 0.4, "IT Support": 0.35, "Academic Support": 0.25}
    core = (
        FakeCore()
        .add(AMBIGUOUS, make_core(p_three, {"medium": 0.9}, set_cat=three))
        .add(CLEAR, make_core({"Transportation": 0.9}, {"medium": 0.9}))
        .add(SAD, make_core({"Academic Support": 0.9}, {"high": 0.9}, flags=frozenset({"distress"})))
    )  # fmt: skip
    c = build_test(core=core, record_sink=True)
    memory, encoder = InMemoryMemoryStore(), FakeEncoder()
    use_case = FeedbackUseCase(c.repo, c.repo, memory, c.act, encoder, c.clock, (c.sink,))
    return Harness(c, memory, encoder, use_case)


def test_it_is_the_feedback_handler_the_route_expects(h: Harness) -> None:
    assert isinstance(h.feedback, FeedbackHandler)


def test_a_correction_finalizes_the_ticket_and_enters_memory(h: Harness) -> None:
    r = h.triage(AMBIGUOUS)
    assert r.status == "human_review" and r.action is not None and r.action.provisional
    pid = h.prediction_id(r.request_id)

    out = h.feedback.run(FeedbackRequest(prediction_id=pid, corrected_category=Category.IT_SUPPORT,
                                         note="portal outage"), STAFF)  # fmt: skip

    assert (out.category, out.priority, out.tier) == (Category.IT_SUPPORT, Priority.MEDIUM, "human")
    assert "staff_confirmed" in out.flags and "needs_review" not in out.flags
    stored = h.c.repo.get_prediction(pid)
    assert stored.category == Category.IT_SUPPORT and stored.tier == "human"
    [review] = h.c.repo.tables["review_queue"].values()
    assert (review["status"], review["corrected_category"], review["reviewer_id"]) == (
        "corrected", "IT Support", STAFF_ID)  # fmt: skip
    assert out.ticket is not None and not out.ticket.provisional
    assert (out.ticket.category, out.ticket.office) == (Category.IT_SUPPORT, "it")
    assert h.c.repo.get_ticket(out.ticket.id).provisional is False
    [example] = h.memory.active()
    assert example.id == out.memory.example_id and out.memory.active_examples == 1
    assert (example.category, example.author_id) == (Category.IT_SUPPORT, STAFF_ID)
    assert example.created_at == h.c.clock.now() and h.encoder.calls == 1  # no core embedding -> encoded
    assert h.c.events("feedback.corrected")


def test_a_plain_confirmation_keeps_the_labels_and_still_teaches(h: Harness) -> None:
    r = h.triage(CLEAR)
    assert r.status == "decided"
    ticket_before = h.c.repo.tables["tickets"][r.action.ticket_id]["status"] if r.action else None
    out = h.feedback.run(FeedbackRequest(prediction_id=h.prediction_id(r.request_id)), ADMIN)
    assert out.category == Category.TRANSPORTATION and "staff_confirmed" in out.flags
    assert out.memory.active_examples == 1 and h.c.events("feedback.confirmed")
    if r.action and r.action.ticket_id:
        assert out.ticket is not None and out.ticket.status == ticket_before


def test_the_core_embedding_is_reused_when_present(h: Harness) -> None:
    r = h.triage(CLEAR)
    pid = h.prediction_id(r.request_id)
    pred = h.c.repo.get_prediction(pid)
    # the codec does not store the embedding; serve the prediction as the live core produced it
    live = dataclasses.replace(pred, core=dataclasses.replace(pred.core, embedding=(1.0, 0.0, 0.0)))
    h.c.repo.get_prediction = lambda _id: live  # type: ignore[method-assign]
    h.feedback.run(FeedbackRequest(prediction_id=pid), STAFF)
    assert h.encoder.calls == 0 and h.memory.active()[0].embedding == (1.0, 0.0, 0.0)


def test_students_and_the_service_token_may_not_review(h: Harness) -> None:
    pid = h.prediction_id(h.triage(CLEAR).request_id)
    for who in (Reviewer("student", alias="demo-17"), Reviewer("service", user_id=None)):
        with pytest.raises(Unauthorized):
            h.feedback.run(FeedbackRequest(prediction_id=pid), who)
    assert h.memory.stats().total == 0


def test_an_unknown_prediction_is_not_found(h: Harness) -> None:
    with pytest.raises(NotFound):
        h.feedback.run(FeedbackRequest(prediction_id="missing"), STAFF)


def test_distress_is_acknowledged_by_admins_only_and_never_learned(h: Harness) -> None:
    r = h.triage(SAD)
    assert r.status == "distress"
    pid = h.prediction_id(r.request_id)
    with pytest.raises(Unauthorized):
        h.feedback.run(FeedbackRequest(prediction_id=pid), STAFF)
    out = h.feedback.run(FeedbackRequest(prediction_id=pid, note="called the student"), ADMIN)
    assert out.memory.example_id == "" and h.memory.stats().total == 0 and out.ticket is None
    [review] = h.c.repo.tables["review_queue"].values()
    assert review["status"] == "confirmed" and review["note"] == "called the student"
    assert h.c.events("feedback.distress_ack")
