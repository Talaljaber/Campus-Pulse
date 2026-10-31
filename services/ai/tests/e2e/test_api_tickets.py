"""P4.9 over HTTP: the signed Linear webhook, the dashboard status route and the SLA loop in the lifespan."""

from __future__ import annotations

import threading
from datetime import timedelta

from fastapi.testclient import TestClient
from fixtures.api import api_client, api_settings, auth
from fixtures.backend_fakes import FakeSink, FrozenClock
from fixtures.containers import BackendTestContainer, build_test
from fixtures.lifecycle import ALIAS, offline_linear, seed_ticket, signature, webhook_body

from campuspulse_ai.composition.api import ApiServices
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
    assert r.json() == {"accepted": True, "ticket_id": ticket.id, "status": "resolved"}
    assert c.repo.get_ticket(ticket.id).status == TicketStatus.RESOLVED
    [note] = c.notifications()  # the background task ran after the response
    assert note["alias"] == ALIAS and note["payload"]["status"] == "resolved"


def test_bad_or_missing_signature_is_401_and_writes_nothing() -> None:
    client, c = linear_api()
    ticket = seed_ticket(c)
    raw = webhook_body(c.clock, ticket.links[0].external_id)
    events = len(c.events())
    for headers in ({}, {"Linear-Signature": "0" * 64}):
        r = client.post(WEBHOOK, content=raw, headers=headers)
        assert r.status_code == 401 and r.json()["error"]["code"] == "unauthenticated"
    assert len(c.events()) == events and c.notifications() == []
    assert c.repo.get_ticket(ticket.id).status == TicketStatus.OPEN


def test_ignored_events_are_acknowledged() -> None:
    client, c = linear_api()
    raw = webhook_body(c.clock, "issue-we-never-created")
    r = client.post(WEBHOOK, content=raw, headers={"Linear-Signature": signature(raw)})
    assert r.status_code == 200 and r.json() == {"accepted": False, "ticket_id": None, "status": None}
    bad = b"[1, 2]"
    assert client.post(WEBHOOK, content=bad, headers={"Linear-Signature": signature(bad)}).status_code == 422


def test_dashboard_status_route() -> None:
    c = build_test()
    client = api_client(c, tickets=c.sync)
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
    assert [link["sink"] for link in out["links"]] == ["linear"]
    assert c.sink.calls == [("update_status", ticket.id)]
    assert c.notifications()[0]["payload"]["message"] == "Technician on the way."
    missing = client.post("/v1/tickets/nope/status", json=body, headers=auth("admin"))
    assert missing.status_code == 404
    assert client.post(url, json={"status": "done"}, headers=auth("admin")).status_code == 422


POLL_S = 0.05
WAIT_S = 5.0


def test_lifespan_runs_the_sla_scanner_at_startup() -> None:
    c = build_test()
    overdue = seed_ticket(c, sla_due_at=c.clock.at - timedelta(minutes=1))
    with TestClient(create_app(ApiServices(sla=c.sla, clock=c.clock), api_settings(sla_scan_minutes=5))):
        waited = 0.0
        while c.repo.get_ticket(overdue.id).status != TicketStatus.ESCALATED and waited < WAIT_S:
            threading.Event().wait(POLL_S)
            waited += POLL_S
    assert c.repo.get_ticket(overdue.id).status == TicketStatus.ESCALATED
    assert len(c.events("sla.escalated")) == 1  # the loop sleeps 5 min between scans


def test_no_scanner_when_disabled() -> None:
    c = build_test()
    overdue = seed_ticket(c, sla_due_at=c.clock.at - timedelta(minutes=1))
    with TestClient(create_app(ApiServices(sla=c.sla, clock=c.clock), api_settings(sla_scan_minutes=0))):
        threading.Event().wait(0.2)
    assert c.repo.get_ticket(overdue.id).status == TicketStatus.OPEN
