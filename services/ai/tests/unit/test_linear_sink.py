"""P4.6: LinearSink (GraphQL over httpx, respx-mocked) and the signed Linear webhook.

Every HTTP call goes through `respx`; an unmatched request fails the test, so nothing reaches
Linear. The replies in `tests/fixtures/linear/` are hand-written in Linear's documented shapes.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
import yaml
from fixtures.backend_fakes import FrozenClock, make_ticket
from pydantic import SecretStr

from campuspulse_ai.adapters.integrations.linear import (
    DEMO_BANNER,
    LinearMapping,
    LinearSink,
    sign,
    verify_signature,
)
from campuspulse_ai.adapters.integrations.retrying import RetryingSink
from campuspulse_ai.domain.entities import Ticket
from campuspulse_ai.domain.errors import InvalidInput, SinkError, Unauthorized
from campuspulse_ai.domain.labels import Category, Priority
from campuspulse_ai.domain.ports import TicketSink
from campuspulse_ai.domain.values import TicketLink, TicketStatus

ROOT = Path(__file__).resolve().parents[4]
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "linear"
API_URL = "https://linear.test/graphql"
API_KEY = "lin_api_TESTKEY0000"  # a fake personal key
SECRET = SecretStr("whsec-test-secret")
TICKET_ID = "c1a9e3b7-2d4f-4e6a-9b8c-7d6e5f4a0003"
REQUEST_ID = "7f1d2c3b-0000-4000-8000-000000000001"
ISSUE_URL = "https://linear.app/campus-pulse/issue/CDP-43/registration-portal-error"


def fixture(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return data


def mapping_dict() -> dict[str, Any]:
    data = yaml.safe_load((ROOT / "config" / "integrations.yaml").read_text(encoding="utf-8"))
    linear: dict[str, Any] = data["linear"]
    linear.update(api_url=API_URL)  # every other value is the committed config (team CDP)
    linear["team_by_office"]["facilities"] = "FAC"
    return linear


Reply = httpx.Response | Exception


@dataclass
class FakeLinear:
    """Dispatches respx calls on the GraphQL operation name and records (operation, variables)."""

    replies: dict[str, list[Reply]] = field(default_factory=dict)
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    headers: list[httpx.Headers] = field(default_factory=list)

    def on(self, op: str, *replies: Reply) -> None:
        self.replies.setdefault(op, []).extend(replies)

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        op = body["query"].split()[1].split("(")[0]
        self.calls.append((op, body["variables"]))
        self.headers.append(request.headers)
        queue = self.replies.get(op)
        if not queue:
            raise AssertionError(f"unexpected Linear call {op}")
        reply = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(reply, Exception):
            raise reply
        return reply

    def ops(self) -> list[str]:
        return [op for op, _ in self.calls]


def ok(name: str) -> httpx.Response:
    return httpx.Response(200, json=fixture(name))


NOT_FOUND = httpx.Response(200, json={"errors": [{"message": "Entity not found"}], "data": None})


@pytest.fixture
def linear() -> Iterator[FakeLinear]:
    fake = FakeLinear()
    with respx.mock(assert_all_called=False) as router:
        router.post(API_URL).mock(side_effect=fake.handler)
        yield fake


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock()


SinkFactory = Callable[..., LinearSink]


@pytest.fixture(scope="module")
def http() -> Iterator[httpx.Client]:
    """One client for the module: building an httpx.Client loads the CA bundle (seconds on Windows)."""
    client = httpx.Client()
    yield client
    client.close()


@pytest.fixture
def make_sink(clock: FrozenClock, http: httpx.Client) -> SinkFactory:
    def build(**overrides: Any) -> LinearSink:
        raw = mapping_dict()
        raw.update(overrides)
        return LinearSink(SecretStr(API_KEY), SECRET, LinearMapping.from_dict(raw), http, clock)

    return build


def linked(ticket: Ticket) -> Ticket:
    ticket.links = [TicketLink(ticket.id, "linear", TICKET_ID, ISSUE_URL)]
    return ticket


# --------------------------------------------------------------------------- outbound


def test_create_sends_one_issue_with_the_mapped_fields(linear: FakeLinear, make_sink: SinkFactory) -> None:
    linear.on("CampusPulseTeams", ok("teams.json"))
    linear.on("CampusPulseLabels", ok("labels.json"))
    linear.on("CampusPulseIssueCreate", ok("issue_create.json"))
    sink = make_sink()
    assert isinstance(sink, TicketSink)
    link = sink.create(make_ticket(REQUEST_ID, id=TICKET_ID))
    assert link == TicketLink(TICKET_ID, "linear", TICKET_ID, ISSUE_URL)
    assert linear.ops() == ["CampusPulseTeams", "CampusPulseLabels", "CampusPulseIssueCreate"]
    issue = linear.calls[-1][1]["input"]
    assert issue["id"] == TICKET_ID and issue["teamId"] == "8b4300c4-0a05-4581-bd9d-b761e8b6ee70"
    assert issue["title"] == "Registration portal error on the last add/drop day"
    assert (
        issue["priority"] == 2
        and issue["dueDate"] == "2026-11-06"
        and issue["labelIds"] == ["lb-registration"]
    )
    assert f"cp-ticket:{TICKET_ID}" in issue["description"] and DEMO_BANNER in issue["description"]
    assert "priority: high" in issue["description"] and "office: registrar" in issue["description"]
    # A personal API key is sent as-is: no "Bearer" prefix (verified against Linear).
    assert all(h["Authorization"] == API_KEY for h in linear.headers)


def test_a_safety_ticket_is_urgent_and_lists_its_tags(linear: FakeLinear, make_sink: SinkFactory) -> None:
    """D-011: the `safety` tag maps to Linear priority 1 on create and on update."""
    linear.on("CampusPulseTeams", ok("teams.json"))
    linear.on("CampusPulseLabels", ok("labels.json"))
    linear.on("CampusPulseIssueCreate", ok("issue_create.json"))
    linear.on("CampusPulseIssueUpdate", ok("issue_update.json"))
    ticket = make_ticket(REQUEST_ID, id=TICKET_ID, office="facilities", category=Category.FACILITIES)
    ticket.tags = ("safety", "exam-in-progress")
    sink = make_sink()
    sink.create(ticket)
    issue = linear.calls[-1][1]["input"]
    assert issue["priority"] == 1 and "tags: safety, exam-in-progress" in issue["description"]
    sink.update_status(ticket)
    assert linear.calls[-1][1]["input"]["priority"] == 1


def test_a_failed_link_does_not_block_a_retry(linear: FakeLinear, make_sink: SinkFactory) -> None:
    """D-011: a link that records a failed push (error set) is not an issue; create tries again."""
    linear.on("CampusPulseTeams", ok("teams.json"))
    linear.on("CampusPulseLabels", ok("labels.json"))
    linear.on("CampusPulseIssueCreate", ok("issue_create.json"))
    ticket = make_ticket(REQUEST_ID, id=TICKET_ID)
    ticket.links = [TicketLink(TICKET_ID, "linear", f"error:{TICKET_ID}", error="Linear timed out")]
    link = make_sink().create(ticket)
    assert link.error is None and linear.ops().count("CampusPulseIssueCreate") == 1


def test_due_date_is_the_amman_date(linear: FakeLinear, make_sink: SinkFactory) -> None:
    linear.on("CampusPulseTeams", ok("teams.json"))
    linear.on("CampusPulseLabels", ok("labels.json"))
    linear.on("CampusPulseIssueCreate", ok("issue_create.json"))
    late = make_ticket(REQUEST_ID, id=TICKET_ID)
    late.sla_due_at = late.sla_due_at.replace(hour=0, minute=30)  # 00:30 Amman = 21:30 UTC the day before
    make_sink().create(late)
    assert linear.calls[-1][1]["input"]["dueDate"] == "2026-11-06"


def test_create_is_idempotent(linear: FakeLinear, make_sink: SinkFactory) -> None:
    linear.on("CampusPulseTeams", ok("teams.json"))
    linear.on("CampusPulseLabels", ok("labels.json"))
    linear.on("CampusPulseIssueCreate", ok("issue_create.json"))
    sink = make_sink()
    first = sink.create(make_ticket(REQUEST_ID, id=TICKET_ID))
    second = sink.create(make_ticket(REQUEST_ID, id=TICKET_ID))
    assert first == second and linear.ops().count("CampusPulseIssueCreate") == 1


def test_a_ticket_that_already_has_a_link_makes_no_http_call(
    linear: FakeLinear, make_sink: SinkFactory
) -> None:
    link = make_sink().create(linked(make_ticket(REQUEST_ID, id=TICKET_ID)))
    assert link.external_id == TICKET_ID and linear.calls == []


def test_a_repeated_create_recovers_the_existing_issue(linear: FakeLinear, make_sink: SinkFactory) -> None:
    linear.on("CampusPulseTeams", ok("teams.json"))
    linear.on("CampusPulseLabels", ok("labels.json"))
    linear.on("CampusPulseIssueCreate", ok("error_duplicate_id.json"))
    linear.on("CampusPulseIssue", ok("issue_lookup.json"))
    link = make_sink().create(make_ticket(REQUEST_ID, id=TICKET_ID))
    assert link.url == ISSUE_URL and linear.ops()[-2:] == ["CampusPulseIssueCreate", "CampusPulseIssue"]


def test_a_timed_out_create_that_reached_linear_is_recovered(
    linear: FakeLinear, make_sink: SinkFactory
) -> None:
    linear.on("CampusPulseTeams", ok("teams.json"))
    linear.on("CampusPulseLabels", ok("labels.json"))
    linear.on("CampusPulseIssueCreate", httpx.ReadTimeout("slow"))
    linear.on("CampusPulseIssue", ok("issue_lookup.json"))
    assert make_sink().create(make_ticket(REQUEST_ID, id=TICKET_ID)).external_id == TICKET_ID


def test_503_is_retried_then_raised(linear: FakeLinear, make_sink: SinkFactory) -> None:
    linear.on("CampusPulseTeams", ok("teams.json"))
    linear.on("CampusPulseLabels", ok("labels.json"))
    linear.on("CampusPulseIssueCreate", httpx.Response(503, text="unavailable"))
    linear.on("CampusPulseIssue", NOT_FOUND)
    sleeps: list[float] = []
    sink = RetryingSink(make_sink(), max_attempts=3, base_backoff_s=0.5, sleep=sleeps.append)
    with pytest.raises(SinkError) as info:
        sink.create(make_ticket(REQUEST_ID, id=TICKET_ID))
    assert info.value.retryable is True and sleeps == [0.5, 1.0]
    assert linear.ops().count("CampusPulseIssueCreate") == 3
    assert linear.ops().count("CampusPulseTeams") == 1  # the team lookup is cached across attempts


@pytest.mark.parametrize(
    ("reply", "retryable"),
    [
        (httpx.Response(429, text="slow down"), True),
        (httpx.Response(502, text="bad gateway"), True),
        (httpx.Response(400, json=fixture("error_rate_limited.json")), True),
        (httpx.Response(200, json=fixture("error_rate_limited.json")), True),
        (httpx.ConnectError("refused"), True),
        (httpx.ReadTimeout("slow"), True),
        (httpx.Response(401, json={"errors": [{"message": "Authentication required"}]}), False),
        (httpx.Response(200, json={"errors": [{"message": "Argument Validation Error"}]}), False),
        (httpx.Response(200, json={"data": {"issueUpdate": {"success": False, "issue": None}}}), False),
        (httpx.Response(200, text="<html>not json</html>"), False),
    ],
    ids=["429", "502", "400-ratelimited", "200-ratelimited", "connect", "timeout", "401", "graphql-error",
         "no-success", "not-json"],
)  # fmt: skip
def test_error_mapping(linear: FakeLinear, make_sink: SinkFactory, reply: Reply, retryable: bool) -> None:
    linear.on("CampusPulseIssueUpdate", reply)
    ticket = linked(make_ticket(REQUEST_ID, id=TICKET_ID, status=TicketStatus.ESCALATED))
    with pytest.raises(SinkError) as info:
        make_sink().update_status(ticket)
    assert info.value.retryable is retryable and API_KEY not in str(info.value)


def test_update_status_moves_to_the_first_state_of_the_type(
    linear: FakeLinear, make_sink: SinkFactory
) -> None:
    linear.on("CampusPulseTeams", ok("teams.json"))
    linear.on("CampusPulseIssueUpdate", ok("issue_update.json"))
    ticket = linked(make_ticket(REQUEST_ID, id=TICKET_ID, status=TicketStatus.IN_PROGRESS))
    make_sink().update_status(ticket)
    op, variables = linear.calls[-1]
    assert variables == {"id": TICKET_ID, "input": {"priority": 2, "stateId": "st-progress"}}


def test_escalation_changes_only_the_priority(linear: FakeLinear, make_sink: SinkFactory) -> None:
    linear.on("CampusPulseIssueUpdate", ok("issue_update.json"))
    ticket = linked(
        make_ticket(REQUEST_ID, id=TICKET_ID, status=TicketStatus.ESCALATED, priority=Priority.HIGH)
    )
    make_sink().update_status(ticket)
    assert linear.calls == [("CampusPulseIssueUpdate", {"id": TICKET_ID, "input": {"priority": 2}})]


def test_close_moves_to_completed(linear: FakeLinear, make_sink: SinkFactory) -> None:
    linear.on("CampusPulseTeams", ok("teams.json"))
    linear.on("CampusPulseIssueUpdate", ok("issue_update.json"))
    make_sink().close(linked(make_ticket(REQUEST_ID, id=TICKET_ID, status=TicketStatus.RESOLVED)))
    assert linear.calls[-1][1]["input"]["stateId"] == "st-done"


def test_merged_moves_to_the_duplicate_state(linear: FakeLinear, make_sink: SinkFactory) -> None:
    linear.on("CampusPulseTeams", ok("teams.json"))
    linear.on("CampusPulseIssueUpdate", ok("issue_update.json"))
    make_sink().update_status(linked(make_ticket(REQUEST_ID, id=TICKET_ID, status=TicketStatus.MERGED)))
    assert linear.calls[-1][1]["input"]["stateId"] == "st-duplicate"


def test_update_without_a_link_is_not_retryable(linear: FakeLinear, make_sink: SinkFactory) -> None:
    with pytest.raises(SinkError) as info:
        make_sink().update_status(make_ticket(REQUEST_ID, id=TICKET_ID))
    assert info.value.retryable is False and linear.calls == []


def test_an_office_without_a_team_is_not_pushed(linear: FakeLinear, make_sink: SinkFactory) -> None:
    with pytest.raises(SinkError) as info:
        make_sink(default_team="").create(make_ticket(REQUEST_ID, id=TICKET_ID))
    assert info.value.retryable is False and linear.calls == []


def test_office_team_and_unknown_label(linear: FakeLinear, make_sink: SinkFactory) -> None:
    linear.on("CampusPulseTeams", ok("teams.json"))
    linear.on("CampusPulseLabels", ok("labels.json"))
    linear.on("CampusPulseIssueCreate", ok("issue_create.json"))
    ticket = make_ticket(
        REQUEST_ID, id=TICKET_ID, office="facilities", category=Category.FACILITIES, provisional=True
    )
    make_sink().create(ticket)
    issue = linear.calls[-1][1]["input"]
    assert issue["teamId"] == "0e4a1b5c-0000-4000-8000-00000000f1ce"
    assert "labelIds" not in issue  # "facilities" is not a label in this workspace: skipped
    assert issue["title"].startswith("[unconfirmed] ") and "provisional" in issue["description"]


def test_unknown_team_key_is_not_retryable(linear: FakeLinear, make_sink: SinkFactory) -> None:
    linear.on("CampusPulseTeams", ok("teams.json"))
    with pytest.raises(SinkError) as info:
        make_sink(default_team="NOPE").create(make_ticket(REQUEST_ID, id=TICKET_ID))
    assert info.value.retryable is False


def test_secrets_are_masked(make_sink: SinkFactory) -> None:
    sink = make_sink()
    assert API_KEY not in repr(sink) and SECRET.get_secret_value() not in repr(sink)


# --------------------------------------------------------------------------- inbound webhook


def webhook(clock: FrozenClock, *, age_s: float = 0.0, **changes: Any) -> bytes:
    body = copy.deepcopy(fixture("webhook_issue_completed.json"))
    body["webhookTimestamp"] = int((clock.at.timestamp() - age_s) * 1000)
    body.update(changes)
    return json.dumps(body).encode("utf-8")


def test_signed_state_change_becomes_an_inbound_event(make_sink: SinkFactory, clock: FrozenClock) -> None:
    raw = webhook(clock)
    event = make_sink().handle_inbound(raw, sign(SECRET, raw))
    assert event is not None
    assert (event.sink, event.external_id, event.status) == ("linear", TICKET_ID, TicketStatus.RESOLVED)
    assert event.occurred_at == clock.at and event.payload["identifier"] == "CDP-43"


@pytest.mark.parametrize(
    ("state_type", "status"),
    [
        ("triage", TicketStatus.OPEN),
        ("backlog", TicketStatus.OPEN),
        ("unstarted", TicketStatus.OPEN),
        ("started", TicketStatus.IN_PROGRESS),
        ("completed", TicketStatus.RESOLVED),
        ("canceled", TicketStatus.CLOSED),
        ("duplicate", TicketStatus.CLOSED),
        ("something_new", None),
    ],
)
def test_state_mapping(
    make_sink: SinkFactory, clock: FrozenClock, state_type: str, status: TicketStatus | None
) -> None:
    data = fixture("webhook_issue_completed.json")["data"]
    data["state"]["type"] = state_type
    raw = webhook(clock, data=data)
    event = make_sink().handle_inbound(raw, sign(SECRET, raw))
    assert (event.status if event else None) == status


def test_bad_signature_is_unauthorized(make_sink: SinkFactory, clock: FrozenClock) -> None:
    raw = webhook(clock)
    sink = make_sink()
    for signature in ("", "0" * 64, sign(SecretStr("another-secret"), raw), sign(SECRET, raw + b" ")):
        with pytest.raises(Unauthorized):
            sink.handle_inbound(raw, signature)


def test_stale_or_missing_timestamp_is_unauthorized(make_sink: SinkFactory, clock: FrozenClock) -> None:
    sink = make_sink()
    for raw in (
        webhook(clock, age_s=61),
        webhook(clock, age_s=-61),
        webhook(clock, webhookTimestamp=None),
        webhook(clock, webhookTimestamp="1793858400000"),
    ):
        with pytest.raises(Unauthorized):
            sink.handle_inbound(raw, sign(SECRET, raw))
    fresh = webhook(clock, age_s=59)
    assert sink.handle_inbound(fresh, sign(SECRET, fresh)) is not None


@pytest.mark.parametrize(
    "changes",
    [
        {"type": "Comment"},
        {"action": "create"},
        {"updatedFrom": {"title": "old title"}},
        {"updatedFrom": None},
    ],
    ids=["comment", "create", "title-only", "no-updated-from"],
)
def test_events_that_are_not_state_changes_are_ignored(
    make_sink: SinkFactory, clock: FrozenClock, changes: dict[str, Any]
) -> None:
    raw = webhook(clock, **changes)
    assert make_sink().handle_inbound(raw, sign(SECRET, raw)) is None


def test_a_signed_body_that_is_not_json_is_invalid(make_sink: SinkFactory) -> None:
    raw = b"not json"
    with pytest.raises(InvalidInput):
        make_sink().handle_inbound(raw, sign(SECRET, raw))


def test_verify_signature_needs_a_secret() -> None:
    assert not verify_signature(SecretStr(""), b"{}", sign(SecretStr(""), b"{}"))
    assert verify_signature(SECRET, b"{}", sign(SECRET, b"{}").upper())


# --------------------------------------------------------------------------- mapping


def test_the_committed_config_loads() -> None:
    mapping = LinearMapping.load(ROOT / "config" / "integrations.yaml")
    assert mapping.api_url == "https://api.linear.app/graphql" and mapping.webhook_tolerance_s == 60
    # One team (CDP) for every office, as set up in the CampusPulse workspace.
    assert mapping.default_team == "CDP" and {mapping.team_key(o) for o in mapping.team_by_office} == {"CDP"}
    assert set(mapping.team_by_office) == {
        "registrar",
        "it",
        "finance",
        "transport",
        "facilities",
        "academic",
    }
    assert mapping.priority_for(Priority.HIGH) == 2 and mapping.priority_for(Priority.LOW, safety=True) == 1


@pytest.mark.parametrize(
    "edit",
    [
        lambda d: d.pop("timezone"),
        lambda d: d.update(extra=1),
        lambda d: d.update(timezone="Mars/Olympus"),
        lambda d: d["priority_map"].pop("safety"),
        lambda d: d["priority_map"].update(high=9),
        lambda d: d["label_by_category"].update(Sports="sports"),
        lambda d: d["state_type_by_status"].pop("merged"),
        lambda d: d["status_by_state_type"].update(started="nope"),
    ],
)
def test_invalid_mapping_is_rejected(edit: Callable[[dict[str, Any]], object]) -> None:
    raw = mapping_dict()
    edit(raw)
    with pytest.raises(ValueError):
        LinearMapping.from_dict(raw)
