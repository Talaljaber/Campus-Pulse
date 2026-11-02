"""Ticket-lifecycle helpers (P4.9): seed a linked ticket, build an offline LinearSink, sign a webhook.

The LinearSink is real (HMAC check, replay window, payload filter) but its HTTP client refuses every
call, so nothing can reach Linear.
"""

from __future__ import annotations

import copy
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from pydantic import SecretStr

from campuspulse_ai.adapters.integrations.linear import LinearMapping, LinearSink, sign
from campuspulse_ai.adapters.notify.email_templates import load_ticket_email_templates
from campuspulse_ai.adapters.store.journey_inmemory import InMemoryJourneyStore
from campuspulse_ai.application.use_cases.offices import OfficeMap
from campuspulse_ai.application.use_cases.ticket_emails import InboxBook, TicketMailer
from campuspulse_ai.application.use_cases.ticket_lifecycle import TicketLifecycleUseCase
from campuspulse_ai.config.paths import CONFIG_DIR
from campuspulse_ai.domain.entities import Request, Ticket
from campuspulse_ai.domain.labels import Category, Priority
from campuspulse_ai.domain.routing import ActionsConfig
from campuspulse_ai.domain.values import RequestStatus, TicketLink, TicketStatus
from fixtures.backend_fakes import FakeNotifier, FrozenClock, make_request, make_ticket
from fixtures.containers import BackendTestContainer, load_yaml

ALIAS = "demo-17"
SECRET = SecretStr("whsec-test-secret")
WEBHOOK_FIXTURE = Path(__file__).resolve().parent / "linear" / "webhook_issue_completed.json"
MS_PER_S = 1000


def _refuse(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"tests must not call Linear: {request.url}")


def offline_linear(clock: FrozenClock) -> LinearSink:
    """A LinearSink with the committed mapping, the test secret and no network."""
    mapping = LinearMapping.load(CONFIG_DIR / "integrations.yaml")
    http = httpx.Client(transport=httpx.MockTransport(_refuse))
    return LinearSink(SecretStr("lin_api_TESTKEY0000"), SECRET, mapping, http, clock)


def seed_ticket(
    c: BackendTestContainer,
    *,
    alias: str = ALIAS,
    office: str = "registrar",
    category: Category = Category.REGISTRATION,
    priority: Priority = Priority.HIGH,
    status: TicketStatus = TicketStatus.NEW,
    sla_due_at: datetime | None = None,
    issue_id: str | None = None,
) -> Ticket:
    """A saved request + ticket with a `linear` link (`issue_id`, default a fresh UUID)."""
    text = "I can't register CS 201 and today is the last day"
    request = c.repo.save_request(
        Request(
            id="",
            alias=alias,
            raw_text=text,
            normalized=make_request(text),
            input_mode="text",
            status=RequestStatus.DECIDED,
            created_at=c.clock.at,
        )
    )
    ticket = c.repo.save_ticket(
        make_ticket(
            request.id,
            office=office,
            category=category,
            priority=priority,
            status=status,
            sla_due_at=sla_due_at,
        )
    )
    issue = issue_id or str(uuid.uuid4())
    c.repo.save_ticket_link(TicketLink(ticket.id, "linear", issue, f"https://linear.test/issue/{issue}"))
    return c.repo.get_ticket(ticket.id)


def webhook_body(clock: FrozenClock, issue_id: str, state_type: str = "completed", **changes: Any) -> bytes:
    """A Linear `Issue` update (state change) for `issue_id`, timestamped at the clock."""
    body: dict[str, Any] = copy.deepcopy(json.loads(WEBHOOK_FIXTURE.read_text(encoding="utf-8")))
    body["webhookTimestamp"] = int(clock.at.timestamp() * MS_PER_S)
    body["data"]["id"] = issue_id
    body["data"]["state"]["type"] = state_type
    body.update(changes)
    return json.dumps(body).encode("utf-8")


def signature(raw: bytes) -> str:
    return sign(SECRET, raw)


REQUESTER_INBOX = "requester@campuspulse.invalid"
OFFICE_INBOX = "office@campuspulse.invalid"
IT_INBOX = "it-desk@campuspulse.invalid"
ADMIN_INBOX = "admin@campuspulse.invalid"


@dataclass
class LifecycleHarness:
    """A `TicketLifecycleUseCase` over a container's repository, a journey store and a FAKE notifier."""

    c: BackendTestContainer
    lifecycle: TicketLifecycleUseCase
    journey: InMemoryJourneyStore
    mail: FakeNotifier


def build_lifecycle(
    c: BackendTestContainer, *, encoder: Any = None, mail: FakeNotifier | None = None
) -> LifecycleHarness:
    """The lifecycle over `c.repo` and `c.sink`; emails go to `mail` (a recording fake, never SMTP)."""
    actions = ActionsConfig.from_dict(load_yaml(CONFIG_DIR / "actions.yaml"))
    mail = mail or FakeNotifier()
    journey = InMemoryJourneyStore(c.repo)
    inboxes = InboxBook(
        student_inbox=REQUESTER_INBOX,
        office_inboxes={"it": IT_INBOX},
        default_office_inbox=OFFICE_INBOX,
        admin_inbox=ADMIN_INBOX,
    )
    mailer = TicketMailer(
        load_ticket_email_templates(CONFIG_DIR / "templates" / "email"), mail, c.clock, inboxes, None
    )
    lifecycle = TicketLifecycleUseCase(
        c.repo,
        journey,
        mailer,
        (c.sink,),
        c.clock,
        actions.sla_hours,
        OfficeMap.from_actions(actions),
        c.messages,
        encoder,
    )
    return LifecycleHarness(c, lifecycle, journey, mail)
