"""P4.9 over HTTP: the signed Linear webhook, the dashboard status route and the SLA loop in the lifespan."""

from __future__ import annotations

import threading
from datetime import timedelta

from fastapi.testclient import TestClient
from fixtures.api import api_client, api_settings, auth
from fixtures.backend_fakes import FakeCore, FakeSink, FrozenClock, make_core
from fixtures.containers import BackendTestContainer, build_test
from fixtures.lifecycle import (
    ALIAS,
    IT_INBOX,
    OFFICE_INBOX,
    REQUESTER_INBOX,
    LifecycleHarness,
    build_lifecycle,
    offline_linear,
    seed_ticket,
    signature,
    webhook_body,
)

from campuspulse_ai.composition.api import ApiServices
from campuspulse_ai.domain.labels import Priority
from campuspulse_ai.domain.values import TicketStatus
from campuspulse_ai.frameworks.fastapi_app import create_app

WEBHOOK = "/v1/integrations/linear/webhook"


def linear_api() -> tuple[TestClient, BackendTestContainer]:
    other = FakeSink(name="other")
    c = build_test(sinks=[offline_linear(FrozenClock()), other])
    c.sink = other
    return api_client(c, tickets=c.sync), c


def test_signed_webhook_resolves_and_needs_no_service_token() -> None:
    client, c = linear_api()
    ticket = seed_ticket(c)
    raw = webhook_body(c.clock, ticket.links[0].external_id)
    r = client.post(WEBHOOK, content=raw, headers={"Linear-Signature": signature(raw)})
    assert r.status_code == 200, r.text
    assert r.json() == {"accepted": True, "ticket_id": ticket.id, "status": "solved"}
    assert c.repo.get_ticket(ticket.id).status == TicketStatus.SOLVED
    [note] = c.notifications()  # the background task ran after the response
    assert note["alias"] == ALIAS and note["payload"]["status"] == "solved"


def test_bad_or_missing_signature_is_401_and_writes_nothing() -> None:
    client, c = linear_api()
    ticket = seed_ticket(c)
    raw = webhook_body(c.clock, ticket.links[0].external_id)
    events = len(c.events())
    for headers in ({}, {"Linear-Signature": "0" * 64}):
        r = client.post(WEBHOOK, content=raw, headers=headers)
        assert r.status_code == 401 and r.json()["error"]["code"] == "unauthenticated"
    assert len(c.events()) == events and c.notifications() == []
    assert c.repo.get_ticket(ticket.id).status == TicketStatus.NEW


def test_ignored_events_are_acknowledged() -> None:
    client, c = linear_api()
    raw = webhook_body(c.clock, "issue-we-never-created")
    r = client.post(WEBHOOK, content=raw, headers={"Linear-Signature": signature(raw)})
    assert r.status_code == 200 and r.json() == {"accepted": False, "ticket_id": None, "status": None}
    bad = b"[1, 2]"
    assert client.post(WEBHOOK, content=bad, headers={"Linear-Signature": signature(bad)}).status_code == 422


def lifecycle_api() -> tuple[TestClient, BackendTestContainer, LifecycleHarness]:
    c = build_test()
    c.repo.add_profile(ALIAS, "student", display_name="Test Student")
    h = build_lifecycle(c)
    return api_client(c, tickets=c.sync, lifecycle=h.lifecycle), c, h


def test_dashboard_status_route() -> None:
    client, c, h = lifecycle_api()
    ticket = seed_ticket(c)
    url = f"/v1/tickets/{ticket.id}/status"
    body = {"status": "in_progress", "note": "Technician on the way."}
    other_office = client.post(url, json=body, headers=auth("staff", office="it"))
    assert other_office.status_code == 403 and other_office.json()["error"]["code"] == "forbidden"
    assert client.post(url, json=body, headers=auth("student", ALIAS)).status_code == 403
    r = client.post(url, json=body, headers=auth("staff", office="registrar"))
    assert r.status_code == 200, r.text
    out = r.json()
    assert (out["id"], out["status"], out["office"]) == (ticket.id, "in_progress", "registrar")
    assert out["awaiting_student"] is True
    assert [link["sink"] for link in out["links"]] == ["linear"]
    assert c.sink.calls == [("update_status", ticket.id)]
    assert c.notifications()[0]["payload"]["message"] == "Technician on the way."
    [mail] = h.mail.sent  # the background task ran: one email, to the requester
    assert mail.to_address == REQUESTER_INBOX and "Technician on the way." in mail.body
    missing = client.post("/v1/tickets/nope/status", json=body, headers=auth("admin"))
    assert missing.status_code == 404
    assert client.post(url, json={"status": "done"}, headers=auth("admin")).status_code == 422
    bad = client.post(url, json={"status": "new"}, headers=auth("admin"))
    assert bad.status_code == 422
    assert "transition in_progress -> new not allowed" in bad.json()["error"]["message"]


def test_comment_route_for_staff_notes_and_requesters() -> None:
    client, c, h = lifecycle_api()
    ticket = seed_ticket(c)
    url = f"/v1/tickets/{ticket.id}/comments"
    staff = auth("staff", "staff-registrar", "registrar")
    r = client.post(url, json={"body": "Send us your student number."}, headers=staff)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ticket"]["status"] == "in_progress" and out["ticket"]["awaiting_student"] is True
    act = out["activity"]
    assert (act["kind"], act["visibility"], act["actor_role"], act["actor_office"]) == (
        "comment",
        "public",
        "staff",
        "registrar",
    )
    assert (act["from_status"], act["to_status"]) == ("new", "in_progress") and act["id"]
    assert [m.to_address for m in h.mail.sent] == [REQUESTER_INBOX]
    note = client.post(url, json={"body": "vendor called", "internal": True}, headers=staff).json()
    assert note["activity"]["kind"] == "note" and note["activity"]["visibility"] == "internal"
    assert len(h.mail.sent) == 1  # notes send nothing
    student = auth("student", ALIAS)
    denied = client.post(url, json={"body": "x", "internal": True}, headers=student)
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "forbidden"
    assert client.post(url, json={"body": "x"}, headers=auth("student", "demo-99")).status_code == 403
    assert client.post(url, json={"body": "x"}, headers=auth("staff", "s", "it")).status_code == 403
    reply = client.post(url, json={"body": "123456"}, headers=student)
    assert reply.status_code == 200 and reply.json()["ticket"]["awaiting_student"] is False
    assert [m.to_address for m in h.mail.sent][-1] == OFFICE_INBOX
    assert client.post(url, json={"body": ""}, headers=staff).status_code == 422
    done = client.post(url, json={"body": "Done.", "status": "solved"}, headers=staff).json()
    assert done["ticket"]["status"] == "solved" and done["activity"]["kind"] == "status"
    assert len(h.journey.activity_for(ticket.id)) == 4


def test_priority_forward_and_student_action_routes() -> None:
    client, c, h = lifecycle_api()
    ticket = seed_ticket(c, priority=Priority.MEDIUM)
    staff = auth("staff", "staff-registrar", "registrar")
    prio = f"/v1/tickets/{ticket.id}/priority"
    r = client.post(prio, json={"priority": "low", "note": "later"}, headers=staff)
    assert r.status_code == 200 and r.json()["priority"] == "low"
    assert r.json()["sla_due_at"] > r.json()["clock_started_at"]
    assert client.post(prio, json={"priority": "urgent"}, headers=staff).status_code == 422
    assert client.post(prio, json={"priority": "high"}, headers=auth("student", ALIAS)).status_code == 403
    fwd = f"/v1/tickets/{ticket.id}/forward"
    f = client.post(fwd, json={"office": "it", "note": "network"}, headers=staff)
    assert f.status_code == 200 and (f.json()["office"], f.json()["status"]) == ("it", "new")
    assert [m.to_address for m in h.mail.sent] == [REQUESTER_INBOX, IT_INBOX]  # requester + new office
    same = client.post(fwd, json={"office": "it"}, headers=auth("staff", "x", "it"))
    assert same.status_code == 422
    url = f"/v1/tickets/{ticket.id}/student-action"
    mine = auth("student", ALIAS)
    assert client.post(url, json={"action": "close"}, headers=auth("student", "demo-99")).status_code == 403
    assert client.post(url, json={"action": "close"}, headers=auth("staff", "x", "it")).status_code == 403
    assert client.post(url, json={"action": "keep_open"}, headers=mine).status_code == 422  # not waiting
    assert client.post(url, json={"action": "nope"}, headers=mine).status_code == 422
    done = client.post(url, json={"action": "close"}, headers=mine)
    assert done.status_code == 200 and done.json()["status"] == "closed"
    assert h.mail.sent[-1].to_address == IT_INBOX


def test_triage_schedules_the_created_follow_up() -> None:
    text = "the portal says my registration is closed but today is the deadline"
    c = build_test(core=FakeCore().add(text, make_core({"Registration": 0.9}, {"high": 0.9})))
    h = build_lifecycle(c)
    client = api_client(c, lifecycle=h.lifecycle)
    r = client.post("/v1/triage", json={"text": text}, headers=auth("student", ALIAS))
    assert r.status_code == 200, r.text
    ticket_id = r.json()["action"]["ticket_id"]
    [created] = h.journey.activity_for(ticket_id)  # the background task ran after the response
    assert created.kind == "created" and created.actor_alias == ALIAS
    assert [m.to_address for m in h.mail.sent] == [REQUESTER_INBOX, OFFICE_INBOX]


def test_ticket_routes_answer_501_when_the_lifecycle_is_not_wired() -> None:
    client = api_client(build_test())
    admin = auth("admin")
    for path, body in (
        ("status", {"status": "closed"}),
        ("forward", {"office": "it"}),
        ("priority", {"priority": "low"}),
        ("comments", {"body": "x"}),
        ("student-action", {"action": "close"}),
    ):
        assert client.post(f"/v1/tickets/x/{path}", json=body, headers=admin).status_code == 501


POLL_S = 0.05
WAIT_S = 5.0


def test_lifespan_runs_the_sla_scanner_at_startup() -> None:
    h = build_lifecycle(build_test())
    c = h.c
    overdue = seed_ticket(c, sla_due_at=c.clock.at - timedelta(minutes=1))
    with TestClient(create_app(ApiServices(sla=h.sla, clock=c.clock), api_settings(sla_scan_minutes=5))):
        waited = 0.0
        while c.repo.get_ticket(overdue.id).reminder_count == 0 and waited < WAIT_S:
            threading.Event().wait(POLL_S)
            waited += POLL_S
    assert c.repo.get_ticket(overdue.id).reminder_count == 1
    assert len(c.events("sla.reminder")) == 1  # the loop sleeps 5 min between scans


def test_no_scanner_when_disabled() -> None:
    h = build_lifecycle(build_test())
    c = h.c
    overdue = seed_ticket(c, sla_due_at=c.clock.at - timedelta(minutes=1))
    with TestClient(create_app(ApiServices(sla=h.sla, clock=c.clock), api_settings(sla_scan_minutes=0))):
        threading.Event().wait(0.2)
    assert c.repo.get_ticket(overdue.id).reminder_count == 0
