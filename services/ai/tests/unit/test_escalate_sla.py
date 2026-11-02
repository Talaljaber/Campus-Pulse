"""P9.4: SlaReminderUseCase (two reminders per clock period), SlaSweeper and the cron route.

Fake notifier only (no SMTP). The container clock is mutable, so a test moves time with `c.clock.at`.
"""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from fixtures.api import api_client, api_settings, auth
from fixtures.backend_fakes import FrozenClock
from fixtures.containers import build_test
from fixtures.lifecycle import (
    ADMIN_INBOX,
    IT_INBOX,
    OFFICE_INBOX,
    LifecycleHarness,
    build_lifecycle,
    seed_ticket,
)

from campuspulse_ai.composition.api import ApiServices
from campuspulse_ai.domain.journey import ActivityKind, Visibility
from campuspulse_ai.domain.labels import Priority
from campuspulse_ai.domain.values import TicketStatus
from campuspulse_ai.frameworks.background import SlaSweeper
from campuspulse_ai.frameworks.fastapi_app import create_app

MIN = timedelta(minutes=1)
HOUR = timedelta(hours=1)  # the high-priority SLA period


class Who:
    def __init__(self, role: str, office: str | None = None, alias: str | None = None) -> None:
        self.role, self.office, self.alias = role, office, alias


def harness() -> LifecycleHarness:
    return build_lifecycle(build_test())


def recipients(h: LifecycleHarness) -> list[str]:
    return [m.to_address for m in h.mail.sent]


def test_reminder_1_goes_to_the_office_only_and_once() -> None:
    h = harness()
    now = h.c.clock.at
    t = seed_ticket(h.c, priority=Priority.HIGH, sla_due_at=now - MIN)
    assert h.sla.run(now) == [t.id]
    assert recipients(h) == [OFFICE_INBOX]
    assert h.c.repo.get_ticket(t.id).reminder_count == 1
    # repeated runs in the same window: nothing
    for later in (now, now + 10 * MIN, now + 59 * MIN):
        assert h.sla.run(later) == []
    assert recipients(h) == [OFFICE_INBOX]


def test_reminder_2_goes_to_office_and_admin_then_it_stops() -> None:
    h = harness()
    now = h.c.clock.at
    t = seed_ticket(h.c, priority=Priority.HIGH, sla_due_at=now - MIN)
    h.sla.run(now)
    assert h.sla.run(now + 59 * MIN) == []  # due + 1 h exactly is not yet "after one more period"
    assert h.sla.run(now + HOUR + 2 * MIN) == [t.id]
    assert recipients(h) == [OFFICE_INBOX, OFFICE_INBOX, ADMIN_INBOX]
    assert h.c.repo.get_ticket(t.id).reminder_count == 2
    assert h.sla.run(now + 5 * HOUR) == [] and h.sla.run(now + 100 * HOUR) == []
    assert len(h.mail.sent) == 3


def test_second_period_follows_the_priority() -> None:
    h = harness()
    now = h.c.clock.at
    t = seed_ticket(h.c, priority=Priority.MEDIUM, sla_due_at=now - MIN)
    h.sla.run(now)
    assert h.sla.run(now + 23 * HOUR) == []  # medium period is 24 h
    assert h.sla.run(now + 25 * HOUR) == [t.id]


def test_a_restart_resets_the_count_and_a_new_reminder_1_follows() -> None:
    h = harness()
    c = h.c
    now = c.clock.at
    t = seed_ticket(c, priority=Priority.HIGH, sla_due_at=now - MIN)
    h.sla.run(now)
    h.sla.run(now + HOUR + 2 * MIN)
    assert c.repo.get_ticket(t.id).reminder_count == 2
    c.clock.at = now + 2 * HOUR
    h.lifecycle.forward(t.id, Who("admin", alias="admin"), "it")
    restarted = c.repo.get_ticket(t.id)
    assert (restarted.reminder_count, restarted.office) == (0, "it")
    h.mail.sent.clear()
    assert h.sla.run(c.clock.at + 30 * MIN) == []  # clock running again, not overdue
    assert h.sla.run(restarted.sla_due_at + MIN) == [t.id]
    assert recipients(h) == [IT_INBOX]


def test_not_overdue_and_finished_tickets_are_skipped() -> None:
    h = harness()
    now = h.c.clock.at
    seed_ticket(h.c, sla_due_at=now + HOUR)
    for status in (TicketStatus.SOLVED, TicketStatus.CLOSED, TicketStatus.MERGED):
        seed_ticket(h.c, status=status, sla_due_at=now - HOUR)
    assert h.sla.run(now) == []
    assert h.mail.sent == []


def test_in_progress_tickets_are_reminded_too() -> None:
    h = harness()
    now = h.c.clock.at
    t = seed_ticket(h.c, status=TicketStatus.IN_PROGRESS, sla_due_at=now - MIN)
    assert h.sla.run(now) == [t.id]


def test_a_lost_claim_sends_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    h = harness()
    now = h.c.clock.at
    t = seed_ticket(h.c, sla_due_at=now - MIN)
    monkeypatch.setattr(h.journey, "claim_reminder", lambda *_a: False)
    assert h.sla.run(now) == []
    assert h.mail.sent == [] and h.c.notifications() == [] and h.c.events("sla.reminder") == []
    assert h.journey.activity_for(t.id) == []


def test_a_claim_leaves_priority_and_status_alone_and_records_the_trail() -> None:
    h = harness()
    now = h.c.clock.at
    t = seed_ticket(h.c, office="it", priority=Priority.HIGH, sla_due_at=now - MIN)
    h.sla.run(now)
    h.sla.run(now + HOUR + 2 * MIN)
    saved = h.c.repo.get_ticket(t.id)
    assert (saved.priority, saved.status, saved.office) == (Priority.HIGH, TicketStatus.NEW, "it")
    assert saved.sla_due_at == t.sla_due_at
    notes = h.c.notifications()
    assert [(n["alias"], n["kind"]) for n in notes] == [("office:it", "ticket_status")] * 2
    rows = [a for a in h.journey.activity_for(t.id) if a.kind == ActivityKind.REMINDER]
    assert [(a.body, a.visibility, a.actor_role) for a in rows] == [
        ("Reminder 1", Visibility.INTERNAL, "system"),
        ("Reminder 2, admin informed", Visibility.INTERNAL, "system"),
    ]
    assert [e["payload"]["level"] for e in h.c.events("sla.reminder")] == [1, 2]


# ---------------------------------------------------------------- sweeper


def test_sweeper_throttles_with_a_fake_clock() -> None:
    clock = FrozenClock()
    calls: list[datetime] = []

    def scan(now: datetime) -> list[str]:
        calls.append(now)
        return []

    sweeper = SlaSweeper(scan, clock, 60)

    async def go() -> None:
        await sweeper.maybe_run()
        clock.at += timedelta(seconds=30)
        await sweeper.maybe_run()
        assert len(calls) == 1
        clock.at += timedelta(seconds=31)
        await sweeper.maybe_run()

    asyncio.run(go())
    assert len(calls) == 2


def test_sweeper_skips_while_a_run_is_in_progress_and_survives_errors() -> None:
    clock = FrozenClock()
    started, release = threading.Event(), threading.Event()
    runs: list[int] = []

    def slow(_now: datetime) -> list[str]:
        runs.append(1)
        started.set()
        release.wait(5)
        return []

    sweeper = SlaSweeper(slow, clock, 0)

    async def go() -> None:
        first = asyncio.create_task(sweeper.maybe_run())
        await asyncio.to_thread(started.wait, 5)
        await sweeper.maybe_run()  # lock held: returns at once
        release.set()
        await first

    asyncio.run(go())
    assert runs == [1]

    def boom(_now: datetime) -> list[str]:
        raise RuntimeError("down")

    asyncio.run(SlaSweeper(boom, clock, 0).maybe_run())  # logged, not raised


# ---------------------------------------------------------------- HTTP


def test_cron_route_is_service_only() -> None:
    h = harness()
    now = h.c.clock.at
    t = seed_ticket(h.c, sla_due_at=now - MIN)
    client = api_client(services=ApiServices(sla=h.sla, clock=h.c.clock))
    for role in ("student", "staff", "admin"):
        r = client.post("/v1/cron/sla", headers=auth(role, "x", "it"))
        assert r.status_code == 403, role
    assert h.mail.sent == []
    ok = client.post("/v1/cron/sla", headers=auth())
    assert ok.status_code == 200
    assert ok.json()["reminded"] == [t.id] and ok.json()["ran_at"].startswith(str(now.year))
    assert client.post("/v1/cron/sla", headers=auth()).json()["reminded"] == []
    assert client.post("/v1/cron/sla").status_code == 401


def test_cron_route_is_501_when_not_wired() -> None:
    assert api_client(services=ApiServices()).post("/v1/cron/sla", headers=auth()).status_code == 501


class _SlowScan:
    def __init__(self) -> None:
        self.gate, self.done = threading.Event(), threading.Event()
        self.seen: list[datetime] = []

    def run(self, now: datetime) -> list[str]:
        self.seen.append(now)
        self.gate.wait(5)  # the response must not wait for this
        self.done.set()
        return []


def test_middleware_sweeps_after_the_response_without_delaying_it() -> None:
    h = harness()
    scan = _SlowScan()
    services = ApiServices(sla=scan, clock=h.c.clock)  # type: ignore[arg-type]
    app = create_app(services, api_settings(sla_sweep_min_interval_s=60))
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200  # returns while the scan is blocked
        assert not scan.done.is_set()
        scan.gate.set()
        assert scan.done.wait(5)
        client.get("/health")
    assert len(scan.seen) == 1  # throttled: the second response did not start another scan
