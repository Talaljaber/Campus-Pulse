"""P4.8: ActUseCase, the action engine (FAQ, ticket, booking, safety alert, provisional, finalize)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fixtures.backend_fakes import FakeCalendar, FakeFAQ, FakeNotifier, FakeSink, make_core, make_request
from fixtures.containers import (
    ADVISOR_EMAIL,
    OFFICE_INBOX,
    STUDENT_INBOX,
    BackendTestContainer,
    act_config,
    build_test,
    load_yaml,
    messages,
)

from campuspulse_ai.adapters.integrations.supabase_sink import SINK_NAME
from campuspulse_ai.application.use_cases.act import RECORD_SINK, ActConfig
from campuspulse_ai.application.use_cases.messages import Messages
from campuspulse_ai.config.paths import CONFIG_DIR
from campuspulse_ai.domain.entities import Prediction, Request
from campuspulse_ai.domain.errors import NotificationError, SinkError, StoreError
from campuspulse_ai.domain.labels import Category, Priority
from campuspulse_ai.domain.values import (
    EvidenceVector,
    FAQHit,
    Location,
    Money,
    RequestStatus,
    Slot,
)

ALIAS = "demo-17"


def save_request(c: BackendTestContainer, text: str = "help", location: Location | None = None) -> Request:
    return c.repo.save_request(
        Request(
            id="",
            alias=ALIAS,
            raw_text=text,
            normalized=make_request(text, location=location),
            input_mode="text",
            status=RequestStatus.DECIDED,
            created_at=c.clock.now(),
        )
    )


def prediction(
    req: Request,
    category: Category,
    priority: Priority,
    *,
    flags: frozenset[str] = frozenset(),
    safety: bool = False,
    evidence: dict[str, bool] | None = None,
) -> Prediction:
    core = make_core({category.value: 0.9}, {priority.value: 0.9}, safety=safety)
    if evidence:
        core.evidence = EvidenceVector(flags=evidence)
    return Prediction("", req.id, category, priority, core, core.tier, set(flags), None, Money(0.0), "v1")


def act(
    c: BackendTestContainer,
    category: Category,
    priority: Priority,
    *,
    provisional: bool = False,
    **kw: object,
) -> tuple[Request, object]:
    req = save_request(c)
    return req, c.act.run(prediction(req, category, priority, **kw), req, provisional)  # type: ignore[arg-type]


def hit(score: float, *, demo: bool = True) -> FAQHit:
    return FAQHit(
        "faq-1",
        "Where is the bus timetable?",
        "Buses leave every 30 minutes from Gate 2.",
        "https://example.invalid/bus",
        demo,
        score,
    )


def tickets(c: BackendTestContainer) -> list[dict[str, object]]:
    return list(c.repo.tables["tickets"].values())


def test_faq_hit_above_tau_answers_from_the_faq() -> None:
    c = build_test(faq=FakeFAQ(hits=[hit(0.95)]))
    _, out = act(c, Category.TRANSPORTATION, Priority.LOW)
    assert out.type == "faq_answer" and out.ticket_id is None and out.faq is not None  # type: ignore[attr-defined]
    assert out.message.startswith("Buses leave every 30 minutes") and out.message.endswith("[demo]")  # type: ignore[attr-defined]
    assert "Source: https://example.invalid/bus" in out.message and tickets(c) == []  # type: ignore[attr-defined]
    assert c.faq.queries == [("help", "en", c.act_config.faq_top_k)]


def test_faq_miss_opens_a_ticket_and_says_so() -> None:
    c = build_test(faq=FakeFAQ(hits=[hit(c_tau := 0.1)]))
    assert c_tau < c.config.thresholds.tau_faq
    _, out = act(c, Category.REGISTRATION, Priority.LOW)
    assert (
        out.type == "ticket" and out.message == "I'm not sure. I've opened a ticket so a person can answer."
    )  # type: ignore[attr-defined]
    assert len(tickets(c)) == 1


def test_faq_store_error_degrades_to_a_ticket() -> None:
    c = build_test(faq=FakeFAQ(error=StoreError("pgvector down")))
    _, out = act(c, Category.ACADEMIC_SUPPORT, Priority.LOW)
    assert out.type == "ticket" and len(tickets(c)) == 1  # type: ignore[attr-defined]


def test_ticket_has_sla_office_links_and_a_student_message() -> None:
    c = build_test()
    req, out = act(c, Category.IT_SUPPORT, Priority.MEDIUM)
    assert out.sla_due_at == c.clock.now() + timedelta(hours=72)  # type: ignore[attr-defined]
    [row] = tickets(c)
    assert (row["office"], row["status"], row["provisional"]) == ("it", "open", False)
    assert [(e.sink, e.external_id) for e in out.external] == [("linear", f"linear-{out.ticket_id}")]  # type: ignore[attr-defined]
    assert c.repo.ticket_by_link("linear", f"linear-{out.ticket_id}").id == out.ticket_id  # type: ignore[attr-defined]
    [note] = c.notifications()
    assert (
        note["alias"] == ALIAS
        and "IT Support" in note["payload"]["message"]
        and "status" not in note["payload"]
    )


def test_a_sink_failure_is_recorded_and_the_next_sink_still_runs() -> None:
    broken = FakeSink(name="linear", script=[SinkError("Linear timed out", retryable=True)])
    after = FakeSink(name="webhook")
    c = build_test(sinks=[broken, after])
    _, out = act(c, Category.FINANCE, Priority.MEDIUM)
    ticket = c.repo.get_ticket(out.ticket_id)  # type: ignore[attr-defined]
    errors = {link.sink: link.error for link in ticket.links}
    assert errors == {"linear": "Linear timed out", "webhook": None}
    assert [e.sink for e in out.external] == ["webhook"] and after.calls  # type: ignore[attr-defined]


def test_the_record_sink_is_not_a_link() -> None:
    assert RECORD_SINK == SINK_NAME
    c = build_test(record_sink=True)
    _, out = act(c, Category.FINANCE, Priority.MEDIUM)
    assert [e.sink for e in out.external] == ["linear"]  # type: ignore[attr-defined]
    assert [link.sink for link in c.repo.get_ticket(out.ticket_id).links] == ["linear"]  # type: ignore[attr-defined]


def test_booking_claims_a_slot_saves_a_case_and_emails_both() -> None:
    c = build_test()
    _, out = act(c, Category.ACADEMIC_SUPPORT, Priority.HIGH)
    assert out.type == "booking" and out.booking is not None and out.ticket_id  # type: ignore[attr-defined]
    assert out.booking.advisor_name == c.advisor.name  # type: ignore[attr-defined]
    assert sorted(m.to_address for m in c.email.sent) == sorted([STUDENT_INBOX, ADVISOR_EMAIL])
    [case] = c.repo.tables["cases"].values()
    assert case["ticket_id"] == out.ticket_id  # type: ignore[attr-defined]
    claimed = [s for s in c.repo.tables["advisor_slots"].values() if s.get("booked_by")]
    assert len(claimed) == 1 and claimed[0]["booked_by"] == STUDENT_INBOX


def test_a_non_allowlisted_attendee_never_reaches_the_calendar() -> None:
    slot = Slot("s1", "adv", datetime(2026, 11, 5, 10, 0), datetime(2026, 11, 5, 10, 30))
    calendar = FakeCalendar(slot=slot)
    c = build_test(calendar=calendar, advisor_email="real.person@gju.edu.jo")
    calendar.slot = Slot(
        "s1", c.advisor.id, c.clock.now() + timedelta(hours=1), c.clock.now() + timedelta(hours=2)
    )
    _, out = act(c, Category.ACADEMIC_SUPPORT, Priority.HIGH)
    assert calendar.booked == [] and out.type == "ticket" and out.booking is None  # type: ignore[attr-defined]
    assert "couldn't book" in out.message and c.email.sent == []  # type: ignore[attr-defined]
    assert c.events("act.booking_refused")


def test_provisional_defers_the_booking_and_finalize_fires_it() -> None:
    calendar = FakeCalendar()
    c = build_test(calendar=calendar)
    calendar.slot = Slot(
        "s1", c.advisor.id, c.clock.now() + timedelta(hours=1), c.clock.now() + timedelta(hours=2)
    )
    _, out = act(c, Category.ACADEMIC_SUPPORT, Priority.HIGH, provisional=True)
    assert out.type == "ticket" and out.provisional and calendar.finds == 0  # type: ignore[attr-defined]
    assert "deferred:booking" in out.tags and "unconfirmed" in out.tags  # type: ignore[attr-defined]
    fired = c.act.finalize(c.repo.get_ticket(out.ticket_id))  # type: ignore[attr-defined]
    assert [a.type for a in fired] == ["booking"] and len(calendar.booked) == 1
    confirmed = c.repo.get_ticket(out.ticket_id)  # type: ignore[attr-defined]
    assert not confirmed.provisional and not any(
        t.startswith("deferred:") or t == "unconfirmed" for t in confirmed.tags
    )
    assert ("update_status", out.ticket_id) in c.sink.calls  # type: ignore[attr-defined]
    assert c.act.finalize(confirmed) == []


def test_safety_alert_fires_even_when_provisional() -> None:
    c = build_test()
    _, out = act(c, Category.IT_SUPPORT, Priority.HIGH, provisional=True, safety=True)
    assert out.type == "safety_alert" and "safety" in out.tags and out.provisional  # type: ignore[attr-defined]
    [alert] = c.email.sent
    assert alert.to_address == OFFICE_INBOX and "call campus security now (demo)" in alert.body
    assert "call campus security now (demo)" in out.message  # type: ignore[attr-defined]
    assert c.repo.get_ticket(out.ticket_id).tags[0] == "safety"  # type: ignore[attr-defined]


def test_transport_alert_is_sent_once_and_deferred_when_provisional() -> None:
    c = build_test()
    _, out = act(c, Category.TRANSPORTATION, Priority.HIGH)
    assert "transport-alert" in out.tags and [m.to_address for m in c.email.sent] == [OFFICE_INBOX]  # type: ignore[attr-defined]
    c2 = build_test()
    _, held = act(c2, Category.TRANSPORTATION, Priority.HIGH, provisional=True)
    assert c2.email.sent == []
    fired = c2.act.finalize(c2.repo.get_ticket(held.ticket_id))  # type: ignore[attr-defined]
    assert len(fired) == 1 and [m.to_address for m in c2.email.sent] == [OFFICE_INBOX]


def test_exam_evidence_tags_the_ticket() -> None:
    c = build_test()
    _, out = act(c, Category.IT_SUPPORT, Priority.HIGH, evidence={"exam_now": True})
    assert out.tags == ["exam-in-progress"]  # type: ignore[attr-defined]


def test_a_failing_notifier_never_fails_the_action() -> None:
    c = build_test(email=FakeNotifier(fail_with=NotificationError("smtp down", retryable=True)))
    _, out = act(c, Category.FACILITIES, Priority.HIGH)
    assert out.type == "safety_alert"  # type: ignore[attr-defined]
    [row] = c.outbox("failed")
    assert row["error"] == "smtp down"


def test_no_inboxes_means_no_emails_but_the_ticket_stands() -> None:
    c = build_test(student_inbox=None, office_inbox=None)
    _, out = act(c, Category.FACILITIES, Priority.HIGH)
    assert out.type == "safety_alert" and c.email.sent == [] and len(tickets(c)) == 1  # type: ignore[attr-defined]


def test_act_config_and_messages_validate() -> None:
    raw = load_yaml(CONFIG_DIR / "act.yaml")
    assert act_config().office_hours.weekdays == (6, 0, 1, 2, 3)
    for broken in ({**raw, "faq_top_k": 0}, {**raw, "extra": 1}, {**raw, "booking": {"department": "x"}}):
        with pytest.raises(ValueError):
            ActConfig.from_dict(broken)
    hours = {**raw["booking"]["office_hours"], "start": "16:00"}
    with pytest.raises(ValueError):
        ActConfig.from_dict({**raw, "booking": {**raw["booking"], "office_hours": hours}})
    msgs = load_yaml(CONFIG_DIR / "templates" / "messages.yaml")
    assert messages().ar.demo_marker
    with pytest.raises(ValueError):
        Messages.from_dict({**msgs, "student": {"en": msgs["student"]["en"]}})
    with pytest.raises(ValueError):
        Messages.from_dict({**msgs, "email": {**msgs["email"], "typo": "x"}})
