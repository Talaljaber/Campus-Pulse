"""LinearSink: CampusPulse tickets as Linear issues, plus the signed inbound webhook (P4.6, UD-2).

GraphQL over httpx to `linear.api_url`. A personal API key goes in the `Authorization` header as
is, with **no** `Bearer` prefix (verified). `httpx` is only imported for typing, so importing this
module (and the offline container) never loads it; the composition root passes an `httpx.Client`.

Operations (field names: docs/integrations.md; UNVERIFIED against a live workspace until
scripts/smoke_linear.py runs in P4.0):
- `teams` (once, cached): team key -> id, and the team's workflow states (id, type, position);
- `issueLabels` (once, cached): label name -> id;
- `issueCreate(input: {id, teamId, title, description, priority, dueDate, labelIds})`. The issue
  id is the CampusPulse ticket UUID, so a retried create can never make a second issue: the
  duplicate is detected and the existing issue is returned;
- `issueUpdate(id, input: {stateId?, priority})` for `update_status` and `close`;
- `issue(id)` to recover an issue after a failed or repeated create.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import SecretStr

from campuspulse_ai.domain.entities import Ticket
from campuspulse_ai.domain.errors import InvalidInput, SinkError, Unauthorized
from campuspulse_ai.domain.labels import CATEGORY_ORDER, PRIORITY_ORDER, Priority
from campuspulse_ai.domain.ports import Clock
from campuspulse_ai.domain.values import InboundEvent, TicketLink, TicketStatus

if TYPE_CHECKING:
    import httpx

SINK_NAME = "linear"
TICKET_MARKER = "cp-ticket:"
DEMO_BANNER = (
    "> Demo data from the CampusPulse prototype (GJU AI Quest 2026). Students are aliases and "
    "advisors are fictional."
)
SAFETY_PRIORITY_KEY = "safety"
_MS_PER_S = 1000
_LINEAR_PRIORITY_MIN, _LINEAR_PRIORITY_MAX = 0, 4  # none .. low
_SERVER_ERROR, _CLIENT_ERROR, _RATE_LIMITED = 500, 400, 429
_RATELIMITED_CODE = "RATELIMITED"
_DUPLICATE = re.compile(r"already exists|duplicate|conflict", re.IGNORECASE)
_LINEAR_KEYS = frozenset(
    {
        "api_url", "timeout_s", "webhook_tolerance_s", "timezone", "default_team", "team_by_office",
        "label_by_category", "priority_map", "state_type_by_status", "status_by_state_type",
    }
)  # fmt: skip

_TEAMS = (
    "query CampusPulseTeams { teams(first: 100) { nodes { id key name "
    "states(first: 100) { nodes { id name type position } } } } }"
)
_LABELS = "query CampusPulseLabels { issueLabels(first: 250) { nodes { id name } } }"
_ISSUE = "query CampusPulseIssue($id: String!) { issue(id: $id) { id identifier url } }"
_CREATE = (
    "mutation CampusPulseIssueCreate($input: IssueCreateInput!) "
    "{ issueCreate(input: $input) { success issue { id identifier url } } }"
)
_UPDATE = (
    "mutation CampusPulseIssueUpdate($id: String!, $input: IssueUpdateInput!) "
    "{ issueUpdate(id: $id, input: $input) { success issue { id identifier url } } }"
)


@dataclass(frozen=True, slots=True)
class LinearMapping:
    """The validated `linear` section of `config/integrations.yaml` (see the file for meanings)."""

    api_url: str
    timeout_s: float
    webhook_tolerance_s: int
    timezone: str
    default_team: str
    team_by_office: Mapping[str, str]
    label_by_category: Mapping[str, str]
    priority_map: Mapping[str, int]
    state_type_by_status: Mapping[TicketStatus, str | None]
    status_by_state_type: Mapping[str, TicketStatus] = field(default_factory=lambda: MappingProxyType({}))

    @classmethod
    def load(cls, path: Path) -> LinearMapping:
        """Read `config/integrations.yaml` and validate its `linear` section (`ValueError`)."""
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("linear"), dict):
            raise ValueError(f"{path}: no `linear` section")
        return cls.from_dict(data["linear"])

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> LinearMapping:
        """Validate a parsed `linear` mapping. Raises `ValueError` naming the bad key."""
        unknown = sorted(set(raw) - _LINEAR_KEYS)
        missing = sorted(_LINEAR_KEYS - set(raw))
        if unknown or missing:
            raise ValueError(f"linear: unknown keys {unknown}, missing keys {missing}")
        try:
            return cls._parse(raw)
        except (TypeError, KeyError, AttributeError, ZoneInfoNotFoundError) as exc:
            raise ValueError(f"linear: invalid value ({exc})") from exc

    @classmethod
    def _parse(cls, raw: Mapping[str, Any]) -> LinearMapping:
        ZoneInfo(str(raw["timezone"]))  # ZoneInfoNotFoundError if the zone does not exist
        priorities = {str(k): int(v) for k, v in dict(raw["priority_map"]).items()}
        wanted = {str(p) for p in PRIORITY_ORDER} | {SAFETY_PRIORITY_KEY}
        in_range = all(_LINEAR_PRIORITY_MIN <= v <= _LINEAR_PRIORITY_MAX for v in priorities.values())
        if set(priorities) != wanted or not in_range:
            raise ValueError(f"linear.priority_map needs exactly {sorted(wanted)} with Linear priorities 0-4")
        categories = {str(c) for c in CATEGORY_ORDER}
        labels = {str(k): str(v) for k, v in dict(raw["label_by_category"]).items()}
        if not set(labels) <= categories:
            extra = sorted(set(labels) - categories)
            raise ValueError(f"linear.label_by_category: unknown categories {extra}")
        out_raw = dict(raw["state_type_by_status"])
        out_states = {TicketStatus(k): (None if v is None else str(v)) for k, v in out_raw.items()}
        if set(out_states) != set(TicketStatus):
            raise ValueError("linear.state_type_by_status must list every ticket status")
        in_states = {str(k): TicketStatus(v) for k, v in dict(raw["status_by_state_type"]).items()}
        teams = {str(k): str(v or "") for k, v in dict(raw["team_by_office"]).items()}
        return cls(
            api_url=str(raw["api_url"]),
            timeout_s=float(raw["timeout_s"]),
            webhook_tolerance_s=int(raw["webhook_tolerance_s"]),
            timezone=str(raw["timezone"]),
            default_team=str(raw["default_team"] or ""),
            team_by_office=MappingProxyType(teams),
            label_by_category=MappingProxyType(labels),
            priority_map=MappingProxyType(priorities),
            state_type_by_status=MappingProxyType(out_states),
            status_by_state_type=MappingProxyType(in_states),
        )

    def team_key(self, office: str) -> str:
        """The configured team key for `office` ("" when neither it nor the default is set)."""
        return self.team_by_office.get(office) or self.default_team

    def priority_for(self, priority: Priority, *, safety: bool = False) -> int:
        return self.priority_map[SAFETY_PRIORITY_KEY if safety else str(priority)]


@dataclass(frozen=True, slots=True)
class _Team:
    id: str
    states: tuple[tuple[str, str, float], ...]  # (id, type, position)

    def state_id(self, state_type: str) -> str | None:
        matches = sorted((pos, sid) for sid, kind, pos in self.states if kind == state_type)
        return matches[0][1] if matches else None


class LinearSink:
    """`TicketSink` for Linear issues (create / update_status / close / handle_inbound).

    - `create(ticket)` is idempotent on `ticket.id`: an existing `linear` link on the ticket (or one
      created earlier by this instance) is returned with no HTTP call; a repeated `issueCreate` for
      the same id is recovered with `issue(id)`.
    - `update_status(ticket)` moves the issue to the first state of the mapped type and sets the
      priority; `close(ticket)` uses the `closed` mapping (completed).
    - `handle_inbound(raw_body, signature)` verifies `Linear-Signature` = hex HMAC-SHA256 of the raw
      body with `LINEAR_WEBHOOK_SECRET` (constant-time compare), rejects a `webhookTimestamp` more
      than `webhook_tolerance_s` from `clock.now()`, and returns an `InboundEvent` only for an
      `Issue` `update` whose `updatedFrom` has `stateId` and whose new state type is mapped; else None.

    Errors: `SinkError(retryable=True)` for timeouts, network errors, 429, 5xx and Linear's
    `RATELIMITED`; `SinkError(retryable=False)` for other 4xx, GraphQL errors, a missing team or
    link; `Unauthorized` for a bad signature or a stale/missing timestamp; `InvalidInput` for a
    signed body that is not JSON. The API key and webhook secret never appear in errors or `repr`.
    """

    def __init__(
        self,
        api_key: SecretStr,
        webhook_secret: SecretStr,
        mapping: LinearMapping,
        http: httpx.Client,
        clock: Clock,
    ) -> None:
        self.name = SINK_NAME
        self._api_key = api_key
        self._secret = webhook_secret
        self._mapping = mapping
        self._http = http
        self._clock = clock
        self._teams: dict[str, _Team] | None = None
        self._labels: dict[str, str] | None = None
        self._created: dict[str, TicketLink] = {}

    def __repr__(self) -> str:
        return f"LinearSink(api_url={self._mapping.api_url!r}, api_key={self._api_key!r})"

    # ------------------------------------------------------------------ outbound

    def create(self, ticket: Ticket) -> TicketLink:
        existing = self._link(ticket)
        if existing is not None:
            return existing
        team = self._team(ticket.office)
        issue_input: dict[str, object] = {
            "teamId": team.id,
            "title": self._title(ticket),
            "description": self._description(ticket),
            "priority": self._mapping.priority_for(ticket.priority),
            "dueDate": ticket.sla_due_at.astimezone(ZoneInfo(self._mapping.timezone)).date().isoformat(),
        }
        label_id = self._label_id(ticket)
        if label_id:
            issue_input["labelIds"] = [label_id]
        stable_id = _is_uuid(ticket.id)
        if stable_id:
            issue_input["id"] = ticket.id
        try:
            data = self._graphql(_CREATE, {"input": issue_input})
            issue = _issue(data, "issueCreate")
        except SinkError as exc:
            # A timeout may hide a created issue, and a repeated create hits the duplicate id.
            may_exist = exc.retryable or _DUPLICATE.search(str(exc)) is not None
            recovered = self._recover(ticket) if stable_id and may_exist else None
            if recovered is None:
                raise
            issue = recovered
        link = TicketLink(ticket_id=ticket.id, sink=SINK_NAME, external_id=issue["id"], url=issue.get("url"))
        self._created[ticket.id] = link
        return link

    def update_status(self, ticket: Ticket) -> None:
        self._update(ticket, ticket.status)

    def close(self, ticket: Ticket) -> None:
        self._update(ticket, TicketStatus.CLOSED)

    def _update(self, ticket: Ticket, status: TicketStatus) -> None:
        link = self._link(ticket)
        if link is None:
            raise SinkError(f"ticket {ticket.id} has no Linear issue", retryable=False)
        issue_input: dict[str, object] = {"priority": self._mapping.priority_for(ticket.priority)}
        state_type = self._mapping.state_type_by_status.get(status)
        if state_type is not None:
            state_id = self._team(ticket.office).state_id(state_type)
            if state_id is None:
                raise SinkError(f"Linear team has no {state_type!r} state", retryable=False)
            issue_input["stateId"] = state_id
        _issue(self._graphql(_UPDATE, {"id": link.external_id, "input": issue_input}), "issueUpdate")

    # ------------------------------------------------------------------ inbound

    def handle_inbound(self, payload: bytes, signature: str) -> InboundEvent | None:
        if not verify_signature(self._secret, payload, signature):
            raise Unauthorized("bad Linear webhook signature")
        try:
            body = json.loads(payload)
        except (UnicodeDecodeError, ValueError) as exc:
            raise InvalidInput("Linear webhook body is not JSON") from exc
        if not isinstance(body, dict):
            raise InvalidInput("Linear webhook body is not a JSON object")
        sent_ms = body.get("webhookTimestamp")
        if isinstance(sent_ms, bool) or not isinstance(sent_ms, int | float):
            raise Unauthorized("Linear webhook has no webhookTimestamp")
        try:
            sent_at = datetime.fromtimestamp(sent_ms / _MS_PER_S, tz=UTC)
        except (OverflowError, OSError, ValueError) as exc:
            raise Unauthorized("Linear webhook has an invalid webhookTimestamp") from exc
        if abs((self._clock.now() - sent_at).total_seconds()) > self._mapping.webhook_tolerance_s:
            raise Unauthorized("stale Linear webhook (timestamp outside the tolerance)")

        data, updated_from = body.get("data"), body.get("updatedFrom")
        if body.get("type") != "Issue" or body.get("action") != "update":
            return None
        if not isinstance(updated_from, dict) or "stateId" not in updated_from or not isinstance(data, dict):
            return None
        state = data.get("state")
        state_type = state.get("type") if isinstance(state, dict) else None
        status = self._mapping.status_by_state_type.get(str(state_type))
        issue_id = data.get("id")
        if status is None or not isinstance(issue_id, str) or not issue_id:
            return None
        return InboundEvent(
            sink=SINK_NAME,
            external_id=issue_id,
            status=status,
            occurred_at=sent_at.astimezone(ZoneInfo(self._mapping.timezone)),
            payload={
                "identifier": _str_or_none(data.get("identifier")),
                "url": _str_or_none(data.get("url")),
                "state_name": _str_or_none(state.get("name") if isinstance(state, dict) else None),
                "state_type": _str_or_none(state_type),
            },
        )

    # ------------------------------------------------------------------ helpers

    def _link(self, ticket: Ticket) -> TicketLink | None:
        for link in ticket.links:
            if link.sink == SINK_NAME:
                return link
        return self._created.get(ticket.id)

    def _recover(self, ticket: Ticket) -> dict[str, Any] | None:
        try:
            data = self._graphql(_ISSUE, {"id": ticket.id})
        except SinkError:
            return None
        issue = data.get("issue")
        return issue if isinstance(issue, dict) and issue.get("id") else None

    def _team(self, office: str) -> _Team:
        key = self._mapping.team_key(office)
        if not key:
            raise SinkError(f"no Linear team configured for office {office!r}", retryable=False)
        if self._teams is None:
            nodes = _nodes(self._graphql(_TEAMS, {}), "teams")
            self._teams = {
                str(n["key"]): _Team(
                    id=str(n["id"]),
                    states=tuple(
                        (str(s["id"]), str(s["type"]), float(s.get("position") or 0))
                        for s in _nodes(n, "states")
                    ),
                )
                for n in nodes
            }
        team = self._teams.get(key)
        if team is None:
            raise SinkError(f"Linear team {key!r} not found in the workspace", retryable=False)
        return team

    def _label_id(self, ticket: Ticket) -> str | None:
        name = self._mapping.label_by_category.get(str(ticket.category))
        if not name:
            return None
        if self._labels is None:
            nodes = _nodes(self._graphql(_LABELS, {}), "issueLabels")
            self._labels = {}
            for n in nodes:
                self._labels.setdefault(str(n["name"]).casefold(), str(n["id"]))
        return self._labels.get(name.casefold())

    @staticmethod
    def _title(ticket: Ticket) -> str:
        title = ticket.title or f"{ticket.category} request ({ticket.priority})"
        return f"[unconfirmed] {title}" if ticket.provisional else title

    def _description(self, ticket: Ticket) -> str:
        due = ticket.sla_due_at.astimezone(ZoneInfo(self._mapping.timezone)).isoformat(timespec="minutes")
        trace = (
            f"category: {ticket.category} | priority: {ticket.priority} | office: {ticket.office} | "
            f"SLA due: {due}"
        )
        if ticket.provisional:
            trace += " | provisional: labels unconfirmed, waiting for staff review"
        body = ticket.body or ticket.title
        return f"{DEMO_BANNER}\n\n{body}\n\n---\n{TICKET_MARKER}{ticket.id}\n{trace}\n"

    def _graphql(self, query: str, variables: Mapping[str, object]) -> dict[str, Any]:
        import httpx  # lazy: keeps httpx out of the offline import graph

        headers = {"Authorization": self._api_key.get_secret_value(), "Content-Type": "application/json"}
        try:
            resp = self._http.post(
                self._mapping.api_url,
                json={"query": query, "variables": dict(variables)},
                headers=headers,
                timeout=self._mapping.timeout_s,
            )
        except httpx.TimeoutException as exc:
            raise SinkError("Linear timed out", retryable=True) from exc
        except httpx.TransportError as exc:
            raise SinkError(f"Linear unreachable ({type(exc).__name__})", retryable=True) from exc
        body = _json_or_none(resp)
        errors = body.get("errors") if isinstance(body, dict) else None
        rate_limited = resp.status_code == _RATE_LIMITED or _has_code(errors, _RATELIMITED_CODE)
        if rate_limited or resp.status_code >= _SERVER_ERROR:
            raise SinkError(f"Linear is unavailable or rate limited ({resp.status_code})", retryable=True)
        if resp.status_code >= _CLIENT_ERROR or errors:
            detail = _first_message(errors)
            raise SinkError(f"Linear rejected the request ({resp.status_code}: {detail})", retryable=False)
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, dict):
            raise SinkError("Linear returned no data", retryable=False)
        return data


def verify_signature(secret: SecretStr, raw_body: bytes, signature: str) -> bool:
    """True when `signature` is the hex HMAC-SHA256 of `raw_body` under `secret` (constant time)."""
    key = secret.get_secret_value().encode("utf-8")
    if not key or not signature:
        return False
    expected = hmac.new(key, raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip().lower())


def sign(secret: SecretStr, raw_body: bytes) -> str:
    """The `Linear-Signature` value for `raw_body` (used by tests and the smoke script)."""
    return hmac.new(secret.get_secret_value().encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def _issue(data: Mapping[str, Any], op: str) -> dict[str, Any]:
    result = data.get(op)
    issue = result.get("issue") if isinstance(result, dict) else None
    if not isinstance(result, dict) or not result.get("success") or not isinstance(issue, dict):
        raise SinkError(f"Linear {op} did not succeed", retryable=False)
    return issue


def _nodes(data: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
    conn = data.get(key)
    nodes = conn.get("nodes") if isinstance(conn, dict) else None
    if not isinstance(nodes, list):
        raise SinkError(f"Linear reply has no {key}", retryable=False)
    return [n for n in nodes if isinstance(n, dict)]


def _json_or_none(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return None


def _has_code(errors: object, code: str) -> bool:
    if not isinstance(errors, list):
        return False
    return any(
        isinstance(e, dict) and isinstance(e.get("extensions"), dict) and e["extensions"].get("code") == code
        for e in errors
    )


def _first_message(errors: object) -> str:
    if isinstance(errors, list) and errors and isinstance(errors[0], dict):
        return str(errors[0].get("message", "error"))
    return "no details"


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True
