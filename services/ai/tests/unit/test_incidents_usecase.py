"""P4.10 Pulse through the triage flow: one incident ticket, merged member tickets, broadcast, resolve.

`build_test(pulse_encoder=...)` wires the real `WindowedCentroidDetector` (tau_inc 0.92, D-015),
`IncidentActions` and `IncidentsUseCase` over `InMemoryRepository` and `LocalNumpyVectorStore`. The
encoder maps Wi-Fi texts to one topic (cosine >= 0.97 to it) and printer texts to 0.89 of it, the
geometry measured on the v1-rc1 encoder.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass

import pytest
from fixtures.api import api_client, auth
from fixtures.backend_fakes import FakeCore, make_core
from fixtures.containers import BackendTestContainer, build_test

from campuspulse_ai.application.dto import TriageRequest, TriageResponse
from campuspulse_ai.application.use_cases.incidents import IncidentsUseCase
from campuspulse_ai.domain.errors import Unauthorized
from campuspulse_ai.domain.values import TicketStatus

DIM = 32
WIFI_COS, OTHER_COS = 0.97, 0.89


def unit(v: Sequence[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


TOPIC = unit([random.Random(1).gauss(0, 1) for _ in range(DIM)])


def toward(cos: float, seed: str) -> list[float]:
    rnd = random.Random(seed)
    g = [rnd.gauss(0, 1) for _ in range(DIM)]
    dot = sum(a * b for a, b in zip(g, TOPIC, strict=True))
    ortho = unit([a - dot * b for a, b in zip(g, TOPIC, strict=True)])
    sin = math.sqrt(1 - cos * cos)
    return unit([cos * b + sin * o for b, o in zip(TOPIC, ortho, strict=True)])


class TopicEncoder:
    dim = DIM
    model_id = "topic"

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        return [toward(WIFI_COS if "wifi" in t.lower() else OTHER_COS, t) for t in texts]


@dataclass(frozen=True)
class Who:
    role: str
    office: str | None = None
    alias: str | None = None


@pytest.fixture
def c() -> BackendTestContainer:
    return build_test(pulse_encoder=TopicEncoder(), record_sink=True)


def incidents(c: BackendTestContainer) -> IncidentsUseCase:
    use_case = c.extras["incidents"]
    assert isinstance(use_case, IncidentsUseCase)
    return use_case


def report(c: BackendTestContainer, n: int, text: str = "", *, simulated: bool = False) -> TriageResponse:
    body = text or f"wifi is down in building M ({n})"
    return c.triage.run(
        TriageRequest(
            text=body, student_alias=f"sim-{n:02d}", location={"building": "M"}, simulated=simulated
        )
    )


def tickets(c: BackendTestContainer) -> list[dict[str, object]]:
    return list(c.repo.tables["tickets"].values())


def creates(c: BackendTestContainer) -> list[str]:
    return [tid for method, tid in c.sink.calls if method == "create"]


def test_third_report_opens_one_incident_ticket_and_merges_the_first_two(c: BackendTestContainer) -> None:
    first, second = report(c, 1), report(c, 2)
    assert first.action is not None and first.action.type == "ticket" and first.action.incident_id is None
    assert second.action is not None and second.action.type == "ticket"
    third = report(c, 3)
    assert third.action is not None and third.action.type == "incident_merge"
    incident_id = third.action.incident_id
    assert incident_id is not None and third.action.external  # the incident ticket's Linear link
    rows = tickets(c)
    incident_tickets = [t for t in rows if "incident" in t["tags"]]  # type: ignore[operator]
    assert len(incident_tickets) == 1 and incident_tickets[0]["incident_id"] == incident_id
    members = [t for t in rows if "incident" not in t["tags"]]  # type: ignore[operator]
    assert {t["status"] for t in members} == {"merged"}
    assert {t["incident_id"] for t in members} == {incident_id}
    # Linear: two own issues, then the incident issue; the third report's own ticket stays in the record
    assert len(creates(c)) == 3 and creates(c)[-1] == incident_tickets[0]["id"]
    updates = [tid for method, tid in c.sink.calls if method == "update_status"]
    assert sorted(updates) == sorted([first.action.ticket_id, second.action.ticket_id])
    # one broadcast per reporter
    assert sorted(n["alias"] for n in c.notifications() if "building M" in str(n["payload"])) == [
        "sim-01", "sim-02", "sim-03"]  # fmt: skip


def test_a_fourth_report_attaches_without_a_new_issue(c: BackendTestContainer) -> None:
    for n in range(1, 4):
        report(c, n)
    before = len(creates(c))
    fourth = report(c, 4)
    assert fourth.action is not None and fourth.action.type == "incident_merge"
    assert len(creates(c)) == before
    [listed] = incidents(c).list(open_only=True)
    assert listed.report_count == 4 and listed.ticket_id is not None
    assert len(listed.member_ticket_ids) == 4 and not listed.simulated
    assert [n["alias"] for n in c.notifications() if "building M" in str(n["payload"])].count("sim-04") == 1


def test_an_unrelated_it_complaint_in_the_same_building_keeps_its_own_ticket(c: BackendTestContainer) -> None:
    for n in range(1, 4):
        report(c, n)
    printer = report(c, 9, "the printer in building M is jammed")
    assert printer.action is not None and printer.action.type == "ticket"
    assert printer.action.incident_id is None


def test_simulated_traffic_marks_requests_and_the_incident(c: BackendTestContainer) -> None:
    for n in range(1, 4):
        report(c, n, simulated=True)
    assert all(r.get("simulated") for r in c.repo.tables["requests"].values())
    [listed] = incidents(c).list(open_only=True)
    assert listed.simulated


def test_resolve_closes_members_and_notifies_each_reporter_once(c: BackendTestContainer) -> None:
    for n in range(1, 5):
        report(c, n)
    [listed] = incidents(c).list(open_only=True)
    with pytest.raises(Unauthorized):
        incidents(c).resolve(listed.id, Who("staff", "finance"))
    before = len(c.notifications())
    out = incidents(c).resolve(listed.id, Who("staff", "it", "staff-it"), "Access point replaced")
    assert out.incident.status == "resolved" and out.notified_reporters == 4
    assert len(out.closed_ticket_ids) == 5  # four reports + the incident ticket
    statuses = {t["id"]: t["status"] for t in tickets(c)}
    assert statuses[listed.ticket_id] == TicketStatus.RESOLVED
    assert {statuses[t] for t in listed.member_ticket_ids} == {TicketStatus.CLOSED}
    assert c.sink.calls[-1] == ("update_status", listed.ticket_id)  # the Linear issue moves to Done
    assert len(c.notifications()) - before == 4
    again = incidents(c).resolve(listed.id, Who("admin"))
    assert again.notified_reporters == 0 and again.closed_ticket_ids == []
    assert incidents(c).list(open_only=True) == []


def test_incident_routes_over_http(c: BackendTestContainer) -> None:
    for n in range(1, 4):
        report(c, n)
    client = api_client(c, incidents=incidents(c))
    listed = client.get("/v1/incidents?open=1", headers=auth("staff", office="it"))
    assert listed.status_code == 200 and len(listed.json()) == 1
    assert client.get("/v1/incidents", headers=auth("staff", office="finance")).json() == []
    incident_id = listed.json()[0]["id"]
    assert client.post(f"/v1/incidents/{incident_id}/resolve", json={},
                       headers=auth("student", "sim-01")).status_code == 403  # fmt: skip
    r = client.post(f"/v1/incidents/{incident_id}/resolve", json={"note": "fixed"}, headers=auth("admin"))
    assert r.status_code == 200 and r.json()["notified_reporters"] == 3


def test_only_scripts_and_admins_can_mark_traffic_simulated(c: BackendTestContainer) -> None:
    client = api_client(c)
    body = {"text": "wifi down in M", "simulated": True, "location": {"building": "M"}}
    student = client.post("/v1/triage", json=body, headers=auth("student", "demo-17")).json()
    service = client.post("/v1/triage", json={**body, "student_alias": "sim-01"}, headers=auth()).json()
    rows = c.repo.tables["requests"]
    assert not rows[student["request_id"]].get("simulated") and rows[service["request_id"]]["simulated"]


def test_d017_the_incident_ticket_follows_the_majority_category() -> None:
    """D-017: reports the model labels differently form one incident; its ticket's office is the
    majority category's and moves (mirrored) when the majority changes."""
    labels = ["Transportation", "IT Support", "Transportation", "IT Support", "IT Support"]
    texts = [f"wifi is down in building M ({n})" for n in range(1, 6)]
    core = FakeCore()
    for text, label in zip(texts, labels, strict=True):
        core.add(text, make_core({label: 0.9}, {"medium": 0.9}))
    c = build_test(core=core, pulse_encoder=TopicEncoder(), record_sink=True)
    out = [report(c, n, text) for n, text in enumerate(texts, start=1)]
    kinds = [r.action.type if r.action else None for r in out]
    assert kinds == ["ticket", "ticket", "incident_merge", "incident_merge", "incident_merge"]
    assert len({r.action.incident_id for r in out[2:] if r.action}) == 1
    [incident] = c.repo.list_incidents(open_only=True, limit=5)
    assert (incident.category, incident.report_count) == ("IT Support", 5)  # 3 of 5
    [ticket] = [t for t in tickets(c) if "incident" in t["tags"]]  # type: ignore[operator]
    assert (ticket["office"], ticket["category"]) == ("it", "IT Support")
    assert str(ticket["title"]).startswith("IT Support reports in building M")
    assert ("update_status", ticket["id"]) in c.sink.calls  # it opened as transport, then moved
