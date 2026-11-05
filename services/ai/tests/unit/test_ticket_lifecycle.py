"""P9.3 ticket lifecycle: every row of PLAN table (d), the forbidden cases, hints and `deliver`.

Unit level over `build_test()` (in-memory repository and journey store, fake sink, FAKE notifier: no
SMTP). Time is frozen at the container's clock, so clock restarts are exact.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import pytest
from fixtures.backend_fakes import FakeCore, FakeNotifier, FakeSink, make_core
from fixtures.containers import BackendTestContainer, build_test
from fixtures.lifecycle import (
    ADMIN_INBOX,
    ALIAS,
    IT_INBOX,
    OFFICE_INBOX,
    REQUESTER_INBOX,
    LifecycleHarness,
    build_lifecycle,
    seed_ticket,
)

from campuspulse_ai.application.dto import TriageRequest
from campuspulse_ai.application.use_cases.ticket_emails import EmailEvent
from campuspulse_ai.application.use_cases.ticket_lifecycle import (
    FORWARDED_TAG,
    LifecycleChange,
)
from campuspulse_ai.domain.entities import Ticket
from campuspulse_ai.domain.errors import InvalidInput, NotFound, RecipientNotAllowed, Unauthorized
from campuspulse_ai.domain.journey import ActivityKind, StudentAction, Visibility
from campuspulse_ai.domain.labels import Category, Priority
from campuspulse_ai.domain.values import TicketStatus

NEW, PROG, SOLVED, CLOSED = (
    TicketStatus.NEW,
    TicketStatus.IN_PROGRESS,
    TicketStatus.SOLVED,
    TicketStatus.CLOSED,
)
HOUR = timedelta(hours=1)


@dataclass(frozen=True)
class Who:
    role: str
    office: str | None = None
    alias: str | None = None


REGISTRAR = Who("staff", "registrar", "staff-registrar")
IT = Who("staff", "it", "staff-it")
ADMIN = Who("admin", alias="admin")
STUDENT = Who("student", alias=ALIAS)
OTHER_STUDENT = Who("student", alias="demo-99")
STAFF_REQUESTER = Who("staff", "registrar", "staff-self")  # owns the request in `own_request`


@pytest.fixture
def h() -> LifecycleHarness:
    c = build_test()
    c.repo.add_profile(ALIAS, "student", display_name="Test Student")
    return build_lifecycle(c)


def seed(h: LifecycleHarness, **kw: Any) -> Ticket:
    extra = {k: kw.pop(k) for k in ("awaiting_student", "reminder_count", "tags", "resolved_at") if k in kw}
    ticket = seed_ticket(h.c, **kw)
    if extra:
        if extra.get("reminder_count"):
            extra["reminder_sent_at"] = h.c.clock.at - HOUR
        ticket = h.c.repo.save_ticket(dataclasses.replace(ticket, **extra))
    return ticket


def now(h: LifecycleHarness) -> Any:
    return h.c.clock.at


def emails(change: LifecycleChange) -> list[tuple[str, str, str | None]]:
    return [(str(e.event), e.audience, e.to) for e in change.emails]


def stored(h: LifecycleHarness, ticket: Ticket) -> Ticket:
    return h.c.repo.get_ticket(ticket.id)


def assert_restarted(h: LifecycleHarness, t: Ticket, hours: int) -> None:
    assert t.clock_started_at == now(h)
    assert t.sla_due_at == now(h) + timedelta(hours=hours)
    assert t.reminder_count == 0 and t.reminder_sent_at is None


def assert_clock_kept(before: Ticket, after: Ticket) -> None:
    assert (after.clock_started_at, after.sla_due_at) == (before.clock_started_at, before.sla_due_at)
    assert (after.reminder_count, after.reminder_sent_at) == (before.reminder_count, before.reminder_sent_at)


# --------------------------------------------------------------------------- row 1


def test_row1_on_created_writes_the_thread_row_and_plans_the_received_emails(h: LifecycleHarness) -> None:
    t = seed(h)
    h.lifecycle.on_created(t.id)
    [a] = h.journey.activity_for(t.id)
    assert a.kind == ActivityKind.CREATED and a.visibility == Visibility.PUBLIC and a.actor_alias == ALIAS
    assert [(m.to_address, m.subject.startswith("[CampusPulse #")) for m in h.mail.sent] == [
        (REQUESTER_INBOX, True),
        (OFFICE_INBOX, True),
    ]


def test_row1_on_created_is_idempotent_and_skips_merged(h: LifecycleHarness) -> None:
    t = seed(h)
    h.lifecycle.on_created(t.id)
    h.lifecycle.on_created(t.id)
    assert len(h.journey.activity_for(t.id)) == 1 and len(h.mail.sent) == 2
    merged = seed(h, status=TicketStatus.MERGED)
    h.lifecycle.on_created(merged.id)
    assert h.journey.activity_for(merged.id) == [] and len(h.mail.sent) == 2
    h.lifecycle.on_created("00000000-0000-4000-8000-000000000000")  # unknown: logged, never raises


# --------------------------------------------------------------------------- rows 2-4: staff comments


def test_row2_staff_comment_on_new_moves_to_in_progress_and_waits(h: LifecycleHarness) -> None:
    t = seed(h)
    ch = h.lifecycle.comment(t.id, REGISTRAR, "Please send your student number.")
    after = stored(h, t)
    assert (after.status, after.awaiting_student) == (PROG, True)
    assert_clock_kept(t, after)
    a = ch.activity
    assert a is not None and a.kind == ActivityKind.COMMENT and a.visibility == Visibility.PUBLIC
    assert (a.from_status, a.to_status, a.actor_role, a.actor_office) == (
        "new",
        "in_progress",
        "staff",
        "registrar",
    )
    assert emails(ch) == [("staff_reply", "requester", REQUESTER_INBOX)]
    assert ch.emails[0].ctx.comment == "Please send your student number."


def test_row3_staff_comment_on_in_progress(h: LifecycleHarness) -> None:
    t = seed(h, status=PROG)
    ch = h.lifecycle.comment(t.id, ADMIN, "Any news?")
    after = stored(h, t)
    assert (after.status, after.awaiting_student) == (PROG, True)
    assert_clock_kept(t, after)
    assert ch.activity is not None and ch.activity.kind == ActivityKind.COMMENT
    assert emails(ch) == [("staff_reply", "requester", REQUESTER_INBOX)]


def test_row4_internal_note_changes_nothing_and_sends_nothing(h: LifecycleHarness) -> None:
    t = seed(h, awaiting_student=False)
    ch = h.lifecycle.comment(t.id, REGISTRAR, "Called the vendor.", internal=True)
    assert stored(h, t) == t
    a = ch.activity
    assert a is not None and a.kind == ActivityKind.NOTE and a.visibility == Visibility.INTERNAL
    assert ch.emails == () and not ch.mirror
    with pytest.raises(InvalidInput):
        h.lifecycle.comment(t.id, REGISTRAR, "x", internal=True, status=SOLVED)


# --------------------------------------------------------------------------- rows 5-8: staff status


def test_row5_in_progress_from_new_with_and_without_comment(h: LifecycleHarness) -> None:
    t = seed(h)
    ch = h.lifecycle.change_status(t.id, REGISTRAR, PROG)
    after = stored(h, t)
    assert (after.status, after.awaiting_student) == (PROG, False)  # no comment: awaiting unchanged
    assert_clock_kept(t, after)
    a = ch.activity
    assert (
        a is not None
        and a.kind == ActivityKind.STATUS
        and (a.from_status, a.to_status) == ("new", "in_progress")
    )
    assert emails(ch) == [("in_progress", "requester", REQUESTER_INBOX)]
    t2 = seed(h)
    ch2 = h.lifecycle.change_status(t2.id, REGISTRAR, PROG, "We are on it.")
    assert stored(h, t2).awaiting_student is True
    assert ch2.activity is not None and ch2.activity.body == "We are on it."
    assert ch2.emails[0].ctx.comment == "We are on it."


def test_row6_solved_pauses_the_clock_and_waits_for_the_requester(h: LifecycleHarness) -> None:
    for start in (NEW, PROG):
        t = seed(h, status=start)
        ch = h.lifecycle.change_status(t.id, REGISTRAR, SOLVED, "Fixed, please check.")
        after = stored(h, t)
        assert (after.status, after.awaiting_student) == (SOLVED, True)
        assert after.resolved_at == now(h)
        assert_clock_kept(t, after)
        assert ch.activity is not None and ch.activity.kind == ActivityKind.STATUS
        assert emails(ch) == [("solved", "requester", REQUESTER_INBOX)]
        assert ch.emails[0].ctx.comment == "Fixed, please check."


def test_row7_closed_stops_the_clock(h: LifecycleHarness) -> None:
    for start in (NEW, PROG, SOLVED):
        t = seed(h, status=start, awaiting_student=start == SOLVED)
        ch = h.lifecycle.change_status(t.id, ADMIN, CLOSED)
        after = stored(h, t)
        assert (after.status, after.awaiting_student) == (CLOSED, False)
        assert_clock_kept(t, after)
        assert emails(ch) == [("closed", "requester", REQUESTER_INBOX)]


def test_row8_staff_reopen_restarts_the_clock(h: LifecycleHarness) -> None:
    for start in (SOLVED, CLOSED):
        t = seed(h, status=start, reminder_count=2, resolved_at=now(h))
        ch = h.lifecycle.change_status(t.id, REGISTRAR, PROG)
        after = stored(h, t)
        assert (after.status, after.awaiting_student, after.resolved_at) == (PROG, False, None)
        assert_restarted(h, after, 1)  # high priority: one hour
        assert emails(ch) == [("reopened", "requester", REQUESTER_INBOX)]


def test_staff_comment_with_status_is_one_status_email(h: LifecycleHarness) -> None:
    t = seed(h)
    ch = h.lifecycle.comment(t.id, REGISTRAR, "Done.", status=SOLVED)
    assert emails(ch) == [("solved", "requester", REQUESTER_INBOX)]
    assert ch.activity is not None and ch.activity.kind == ActivityKind.STATUS and ch.activity.body == "Done."
    h.lifecycle.deliver(ch)
    assert len(h.mail.sent) == 1 and "Done." in h.mail.sent[0].body


def test_same_status_is_a_noop_without_email(h: LifecycleHarness) -> None:
    t = seed(h, status=PROG)
    ch = h.lifecycle.change_status(t.id, REGISTRAR, PROG)
    assert ch.activity is None and ch.emails == () and stored(h, t) == t
    h.lifecycle.deliver(ch)
    assert h.mail.sent == [] and h.c.sink.calls == []
    with_note = h.lifecycle.change_status(t.id, REGISTRAR, PROG, "still working")  # a comment counts
    assert with_note.activity is not None and with_note.activity.kind == ActivityKind.COMMENT


@pytest.mark.parametrize(
    ("start", "target"),
    [(PROG, NEW), (SOLVED, NEW), (CLOSED, SOLVED), (CLOSED, TicketStatus.MERGED), (SOLVED, SOLVED)],
)
def test_status_transitions_the_table_does_not_allow(
    h: LifecycleHarness, start: TicketStatus, target: TicketStatus
) -> None:
    t = seed(h, status=start)
    if start == target:  # a no-op, not an error
        assert h.lifecycle.change_status(t.id, REGISTRAR, target).activity is None
        return
    with pytest.raises(InvalidInput, match=f"transition {start} -> {target} not allowed"):
        h.lifecycle.change_status(t.id, REGISTRAR, target)
    assert stored(h, t) == t


def test_staff_public_comment_on_a_solved_ticket_is_refused(h: LifecycleHarness) -> None:
    t = seed(h, status=SOLVED)
    with pytest.raises(InvalidInput):
        h.lifecycle.comment(t.id, REGISTRAR, "hello")


# --------------------------------------------------------------------------- row 9: forward


def test_row9_forward_moves_the_ticket_and_restarts_the_clock(h: LifecycleHarness) -> None:
    for start in (NEW, PROG):
        t = seed(h, status=start, reminder_count=1, awaiting_student=True)
        ch = h.lifecycle.forward(t.id, REGISTRAR, " it ", "Portal outage, not a registration issue.")
        after = stored(h, t)
        assert (after.office, after.category, after.status) == ("it", Category.IT_SUPPORT, NEW)
        assert after.awaiting_student is False and FORWARDED_TAG in after.tags
        assert after.priority == Priority.HIGH
        assert_restarted(h, after, 1)
        a = ch.activity
        assert a is not None and a.kind == ActivityKind.FORWARD
        assert (a.from_office, a.to_office, a.body) == (
            "registrar",
            "it",
            "Portal outage, not a registration issue.",
        )
        assert emails(ch) == [("forwarded", "requester", REQUESTER_INBOX), ("forwarded", "office", IT_INBOX)]
        assert ch.mirror and ch.from_office == "registrar"


def test_forward_errors(h: LifecycleHarness) -> None:
    t = seed(h)
    with pytest.raises(InvalidInput):
        h.lifecycle.forward(t.id, REGISTRAR, "registrar")  # same office
    with pytest.raises(InvalidInput):
        h.lifecycle.forward(t.id, REGISTRAR, "library")
    with pytest.raises(Unauthorized):
        h.lifecycle.forward(t.id, IT, "finance")  # not the ticket's office
    with pytest.raises(NotFound):
        h.lifecycle.forward("00000000-0000-4000-8000-000000000000", ADMIN, "it")
    for status in (SOLVED, CLOSED):
        done = seed(h, status=status)
        with pytest.raises(InvalidInput, match="not allowed"):
            h.lifecycle.forward(done.id, ADMIN, "it")
    assert stored(h, t) == t


# --------------------------------------------------------------------------- row 10: priority


def test_row10_priority_change_restarts_with_the_new_period_and_sends_no_email(h: LifecycleHarness) -> None:
    t = seed(h, status=PROG, awaiting_student=True, reminder_count=2)
    ch = h.lifecycle.change_priority(t.id, REGISTRAR, Priority.LOW, "not urgent")
    after = stored(h, t)
    assert (after.priority, after.status, after.awaiting_student) == (Priority.LOW, PROG, True)
    assert_restarted(h, after, 48)
    a = ch.activity
    assert a is not None and a.kind == ActivityKind.PRIORITY
    assert (a.from_priority, a.to_priority, a.body) == ("high", "low", "not urgent")
    assert ch.emails == () and ch.mirror
    again = h.lifecycle.change_priority(t.id, REGISTRAR, Priority.LOW)
    assert again.activity is None  # same priority: no-op
    up = h.lifecycle.change_priority(t.id, REGISTRAR, Priority.MEDIUM)
    assert stored(h, t).sla_due_at == now(h) + 24 * HOUR and up.activity is not None


def test_raise_priority_lifts_a_new_ticket_restarts_the_clock_and_never_lowers(h: LifecycleHarness) -> None:
    t = seed(h, priority=Priority.MEDIUM)
    ch = h.lifecycle.raise_priority(t.id, Priority.HIGH)
    after = stored(h, t)
    assert after.priority == Priority.HIGH
    assert_restarted(h, after, 1)
    a = ch.activity
    assert a is not None and a.kind == ActivityKind.PRIORITY and a.actor_role == "system"
    assert (a.from_priority, a.to_priority) == ("medium", "high")
    assert ch.emails == () and ch.mirror
    for same_or_lower in (Priority.HIGH, Priority.MEDIUM, Priority.LOW):
        assert h.lifecycle.raise_priority(t.id, same_or_lower).activity is None
    assert stored(h, t).priority == Priority.HIGH


def test_raise_priority_also_lifts_a_ticket_in_progress(h: LifecycleHarness) -> None:
    t = seed(h, priority=Priority.LOW, status=PROG)
    assert h.lifecycle.raise_priority(t.id, Priority.HIGH).activity is not None
    after = stored(h, t)
    assert (after.priority, after.status) == (Priority.HIGH, PROG)
    assert_restarted(h, after, 1)


def test_raise_priority_leaves_a_finished_ticket_alone(h: LifecycleHarness) -> None:
    for status in (SOLVED, CLOSED):
        t = seed(h, priority=Priority.LOW, status=status)
        assert h.lifecycle.raise_priority(t.id, Priority.HIGH).activity is None
        assert stored(h, t).priority == Priority.LOW


def test_priority_needs_a_running_ticket_and_office_staff(h: LifecycleHarness) -> None:
    done = seed(h, status=SOLVED)
    with pytest.raises(InvalidInput):
        h.lifecycle.change_priority(done.id, REGISTRAR, Priority.LOW)
    with pytest.raises(Unauthorized):
        h.lifecycle.change_priority(seed(h).id, IT, Priority.LOW)
    with pytest.raises(Unauthorized):
        h.lifecycle.change_priority(seed(h).id, STUDENT, Priority.LOW)


# --------------------------------------------------------------------------- rows 11-12: requester comment


def test_row11_requester_comment_on_a_running_ticket(h: LifecycleHarness) -> None:
    for start in (NEW, PROG):
        t = seed(h, status=start, awaiting_student=True)
        ch = h.lifecycle.comment(t.id, STUDENT, "My student number is 123.")
        after = stored(h, t)
        assert (after.status, after.awaiting_student) == (start, False)
        assert_clock_kept(t, after)
        assert ch.activity is not None and ch.activity.kind == ActivityKind.COMMENT
        assert ch.activity.actor_role == "student"
        assert emails(ch) == [("requester_reply", "office", OFFICE_INBOX)]


def test_row11_a_forwarded_ticket_also_tells_the_admin_inbox(h: LifecycleHarness) -> None:
    t = seed(h, tags=(FORWARDED_TAG,))
    ch = h.lifecycle.comment(t.id, STUDENT, "Any update?")
    assert emails(ch) == [
        ("requester_reply", "office", OFFICE_INBOX),
        ("requester_reply", "office", ADMIN_INBOX),
    ]
    h.lifecycle.deliver(ch)
    assert [m.to_address for m in h.mail.sent] == [OFFICE_INBOX, ADMIN_INBOX]


def test_row12_requester_comment_reopens_a_solved_or_closed_ticket(h: LifecycleHarness) -> None:
    for start in (SOLVED, CLOSED):
        t = seed(h, status=start, reminder_count=2, resolved_at=now(h))
        ch = h.lifecycle.comment(t.id, STUDENT, "It broke again.")
        after = stored(h, t)
        assert (after.status, after.awaiting_student, after.resolved_at) == (PROG, False, None)
        assert_restarted(h, after, 1)
        a = ch.activity
        assert a is not None and a.kind == ActivityKind.COMMENT
        assert (a.from_status, a.to_status) == (str(start), "in_progress")
        assert emails(ch) == [("reopened", "office", OFFICE_INBOX)]


# --------------------------------------------------------------------------- rows 13-15: requester buttons


def test_row13_requester_solved(h: LifecycleHarness) -> None:
    for start in (PROG, SOLVED):
        t = seed(h, status=start, awaiting_student=True)
        ch = h.lifecycle.student_action(t.id, STUDENT, StudentAction.SOLVED)
        after = stored(h, t)
        assert (after.status, after.awaiting_student) == (SOLVED, False)
        assert_clock_kept(t, after)
        a = ch.activity
        assert a is not None and a.kind == ActivityKind.STUDENT_ACTION and a.body == "solved"
        assert emails(ch) == [("solved", "office", OFFICE_INBOX)]
    repeat = h.lifecycle.student_action(t.id, STUDENT, StudentAction.SOLVED)
    assert repeat.activity is None  # already confirmed: a no-op
    with pytest.raises(InvalidInput):
        h.lifecycle.student_action(seed(h).id, STUDENT, StudentAction.SOLVED)  # still new


def test_row14_requester_close(h: LifecycleHarness) -> None:
    for start in (NEW, PROG, SOLVED):
        t = seed(h, status=start, awaiting_student=True)
        ch = h.lifecycle.student_action(t.id, STUDENT, StudentAction.CLOSE)
        after = stored(h, t)
        assert (after.status, after.awaiting_student) == (CLOSED, False)
        assert_clock_kept(t, after)
        assert emails(ch) == [("closed", "office", OFFICE_INBOX)]


def test_row15_requester_keep_open_restarts_the_clock(h: LifecycleHarness) -> None:
    waiting = seed(h, status=PROG, awaiting_student=True, reminder_count=1)
    ch = h.lifecycle.student_action(waiting.id, STUDENT, StudentAction.KEEP_OPEN)
    after = stored(h, waiting)
    assert (after.status, after.awaiting_student) == (PROG, False)
    assert_restarted(h, after, 1)
    assert emails(ch) == [("reopened", "office", OFFICE_INBOX)]
    solved = seed(h, status=SOLVED, awaiting_student=True, resolved_at=now(h))
    h.lifecycle.student_action(solved.id, STUDENT, StudentAction.KEEP_OPEN)
    assert (stored(h, solved).status, stored(h, solved).resolved_at) == (PROG, None)
    for bad in (seed(h), seed(h, status=PROG, awaiting_student=False), seed(h, status=CLOSED)):
        with pytest.raises(InvalidInput):
            h.lifecycle.student_action(bad.id, STUDENT, StudentAction.KEEP_OPEN)


# --------------------------------------------------------------------------- row 17: hint applied


def test_row17_apply_hint_reroutes_a_new_ticket_without_email_or_hint_row(h: LifecycleHarness) -> None:
    t = seed(h, priority=Priority.MEDIUM)
    ch = h.lifecycle.apply_hint(t.id, Category.IT_SUPPORT, Priority.HIGH)
    after = stored(h, t)
    assert (after.office, after.category, after.priority, after.status) == (
        "it",
        Category.IT_SUPPORT,
        Priority.HIGH,
        NEW,
    )
    assert_restarted(h, after, 1)
    a = ch.activity
    assert (
        a is not None
        and a.kind == ActivityKind.FORWARD
        and a.actor_role == "system"
        and a.body == "past correction"
    )
    assert (a.from_office, a.to_office) == ("registrar", "it")
    assert ch.emails == ()
    assert h.journey._hints == []  # noqa: SLF001 - no hint row for a system re-route
    assert FORWARDED_TAG not in after.tags


def test_row17_apply_hint_priority_is_raise_only(h: LifecycleHarness) -> None:
    t = seed(h, priority=Priority.HIGH)
    h.lifecycle.apply_hint(t.id, Category.FINANCE, Priority.LOW)
    after = stored(h, t)
    assert (after.office, after.priority) == ("finance", Priority.HIGH)
    same = seed(h, priority=Priority.HIGH)
    assert h.lifecycle.apply_hint(same.id, Category.REGISTRATION, Priority.LOW).activity is None
    assert stored(h, same) == same
    with pytest.raises(InvalidInput):
        h.lifecycle.apply_hint(seed(h, status=PROG).id, Category.FINANCE, Priority.HIGH)


# --------------------------------------------------------------------------- hints on forward / priority


class CountingEncoder:
    dim = 3
    model_id = "fake"

    def encode(self, texts: Any) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]


def decided_ticket(c: BackendTestContainer) -> Ticket:
    text = "the portal says my registration is closed but today is the deadline"
    c.core.add(text, make_core({"Registration": 0.9}, {"medium": 0.9}))
    r = c.triage.run(TriageRequest(text=text, student_alias=ALIAS))
    assert r.action is not None and r.action.ticket_id
    return c.repo.get_ticket(r.action.ticket_id)


def test_forward_and_priority_write_hints_with_the_model_labels() -> None:
    c = build_test(core=FakeCore())
    h = build_lifecycle(c, encoder=CountingEncoder())
    t = decided_ticket(c)
    h.lifecycle.forward(t.id, Who("staff", t.office, "staff-x"), "it", "wrong office")
    h.lifecycle.change_priority(t.id, IT, Priority.HIGH)
    fwd, pri = h.journey._hints  # noqa: SLF001
    assert (fwd.kind, fwd.model_category, fwd.model_priority) == ("forward", "Registration", "medium")
    assert (fwd.corrected_category, fwd.corrected_priority, fwd.note) == (
        "IT Support",
        "medium",
        "wrong office",
    )
    assert fwd.embedding == (1.0, 0.0, 0.0) and fwd.ticket_id == t.id and fwd.author_alias == "staff-x"
    assert fwd.request_text.startswith("the portal says")
    assert (pri.kind, pri.corrected_category, pri.corrected_priority) == ("priority", "IT Support", "high")
    matches = h.journey.nearest_hints([1.0, 0.0, 0.0], 3, 0.85)
    assert len(matches) == 2  # both hints share the request embedding
    match = matches[0]
    assert match.corrected_category == "IT Support"


def test_hint_without_an_encoder_has_no_embedding_and_a_failing_encoder_does_not_fail_the_action() -> None:
    c = build_test()
    h = build_lifecycle(c)
    t = seed_ticket(c)
    h.lifecycle.forward(t.id, REGISTRAR, "it")
    [hint] = h.journey._hints  # noqa: SLF001
    assert hint.embedding is None and hint.model_category is None  # no prediction stored for this ticket

    class Boom:
        dim = 3
        model_id = "boom"

        def encode(self, texts: Any) -> list[list[float]]:
            raise RuntimeError("no encoder")

    h2 = build_lifecycle(c, encoder=Boom())
    t2 = seed_ticket(c)
    h2.lifecycle.change_priority(t2.id, REGISTRAR, Priority.LOW)
    assert c.repo.get_ticket(t2.id).priority == Priority.LOW and h2.journey._hints[0].embedding is None  # noqa: SLF001


# --------------------------------------------------------------------------- forbidden cases


def test_requester_cannot_add_internal_notes_or_set_statuses(h: LifecycleHarness) -> None:
    t = seed(h)
    with pytest.raises(Unauthorized):
        h.lifecycle.comment(t.id, STUDENT, "secret", internal=True)
    with pytest.raises(Unauthorized):
        h.lifecycle.comment(t.id, STUDENT, "solved it", status=SOLVED)
    with pytest.raises(Unauthorized):
        h.lifecycle.change_status(t.id, STUDENT, SOLVED)
    with pytest.raises(Unauthorized):
        h.lifecycle.forward(t.id, STUDENT, "it")
    assert stored(h, t) == t and h.journey.activity_for(t.id) == []


def test_other_people_and_other_offices_are_forbidden(h: LifecycleHarness) -> None:
    t = seed(h)
    for who in (OTHER_STUDENT, IT, Who("service"), Who("staff", None, "x")):
        with pytest.raises(Unauthorized):
            h.lifecycle.comment(t.id, who, "hi")
        with pytest.raises(Unauthorized):
            h.lifecycle.change_status(t.id, who, PROG)
        with pytest.raises(Unauthorized):
            h.lifecycle.student_action(t.id, who, StudentAction.CLOSE)


def test_staff_on_their_own_request_act_as_the_requester(h: LifecycleHarness) -> None:
    t = seed(h, alias="staff-self", status=PROG, awaiting_student=True)
    with pytest.raises(Unauthorized):
        h.lifecycle.change_status(t.id, STAFF_REQUESTER, SOLVED)
    with pytest.raises(Unauthorized):
        h.lifecycle.forward(t.id, STAFF_REQUESTER, "it")
    with pytest.raises(Unauthorized):
        h.lifecycle.change_priority(t.id, STAFF_REQUESTER, Priority.LOW)
    with pytest.raises(Unauthorized):
        h.lifecycle.comment(t.id, STAFF_REQUESTER, "private", internal=True)
    ch = h.lifecycle.comment(t.id, STAFF_REQUESTER, "my own reply")  # requester path: row 11
    assert emails(ch)[0][:2] == ("requester_reply", "office") and not stored(h, t).awaiting_student
    ch = h.lifecycle.student_action(t.id, STAFF_REQUESTER, StudentAction.CLOSE)
    assert stored(h, t).status == CLOSED
    admin_own = seed(h, alias="admin")
    ch2 = h.lifecycle.comment(admin_own.id, ADMIN, "admin as requester")
    assert emails(ch2)[0][:2] == ("requester_reply", "office") and ch is not None


def test_a_merged_ticket_accepts_no_action(h: LifecycleHarness) -> None:
    t = seed(h, status=TicketStatus.MERGED)
    calls: list[Any] = [
        lambda: h.lifecycle.comment(t.id, REGISTRAR, "x"),
        lambda: h.lifecycle.comment(t.id, STUDENT, "x"),
        lambda: h.lifecycle.change_status(t.id, REGISTRAR, PROG),
        lambda: h.lifecycle.forward(t.id, REGISTRAR, "it"),
        lambda: h.lifecycle.change_priority(t.id, REGISTRAR, Priority.LOW),
        lambda: h.lifecycle.student_action(t.id, STUDENT, StudentAction.CLOSE),
        lambda: h.lifecycle.apply_hint(t.id, Category.FINANCE, Priority.HIGH),
    ]
    for call in calls:
        with pytest.raises(InvalidInput, match="merged"):
            call()


def test_empty_comment_is_refused(h: LifecycleHarness) -> None:
    with pytest.raises(InvalidInput):
        h.lifecycle.comment(seed(h).id, REGISTRAR, "   ")


# --------------------------------------------------------------------------- deliver


def test_deliver_sends_exactly_one_email_per_change_and_mirrors(h: LifecycleHarness) -> None:
    t = seed(h)
    ch = h.lifecycle.change_status(t.id, REGISTRAR, SOLVED, "Fixed.")
    h.lifecycle.deliver(ch)
    assert len(h.mail.sent) == 1 and h.mail.sent[0].to_address == REQUESTER_INBOX
    assert h.mail.sent[0].subject.startswith("[CampusPulse #") and h.mail.sent[0].html
    assert h.c.sink.calls == [("update_status", t.id)]
    [note] = [n for n in h.c.notifications() if n["alias"] == ALIAS]
    assert note["kind"] == "ticket_status" and note["payload"]["status"] == "solved"
    assert note["payload"]["message"] == "Fixed."
    h.mail.sent.clear()
    h.lifecycle.deliver(h.lifecycle.comment(seed(h).id, REGISTRAR, "internal", internal=True))
    assert h.mail.sent == []  # a note sends nothing


def test_deliver_never_raises_and_a_failing_part_does_not_stop_the_rest() -> None:
    mail = FakeNotifier(fail_with=RecipientNotAllowed("not on the allow-list"))
    c = build_test(sinks=[FakeSink(name="linear", script=[RuntimeError("linear down")] * 5)])
    c.repo.add_profile(ALIAS, "student")
    h = build_lifecycle(c, mail=mail)
    t = seed_ticket(c)
    ch = h.lifecycle.forward(t.id, REGISTRAR, "it", "note")
    h.lifecycle.deliver(ch)  # sink raises, notifier refuses: nothing escapes
    assert len(mail.sent) == 2  # both emails were still attempted
    assert [n for n in c.notifications() if n["alias"] == "office:it"]  # the office was told in-app


def test_forward_ticket_title_is_relabelled(h: LifecycleHarness) -> None:
    t = seed(h)
    h.c.repo.save_ticket(dataclasses.replace(t, title="Registration/high: portal error"))
    h.lifecycle.forward(t.id, REGISTRAR, "it")
    assert stored(h, t).title == "IT Support/high: portal error"


def test_event_names_for_the_audit_trail(h: LifecycleHarness) -> None:
    t = seed(h)
    h.lifecycle.comment(t.id, REGISTRAR, "a")
    h.lifecycle.comment(t.id, REGISTRAR, "n", internal=True)
    h.lifecycle.change_status(t.id, REGISTRAR, SOLVED)
    h.lifecycle.student_action(t.id, STUDENT, StudentAction.CLOSE)
    h.lifecycle.forward(seed(h).id, REGISTRAR, "it")
    h.lifecycle.change_priority(seed(h).id, REGISTRAR, Priority.LOW)
    names = {e["action"] for e in h.c.events()}
    assert {"ticket.comment", "ticket.note", "ticket.status", "ticket.student_action", "ticket.forwarded",
            "ticket.priority"} <= names  # fmt: skip
    assert EmailEvent.STAFF_REPLY.value == "staff_reply"
