"""Opt-in live Linear check (P4.0, Linear part): verify every GraphQL operation LinearSink uses.

Against the real workspace (CampusPulse, team CDP) it runs, in order:
  1. `viewer`        who the key belongs to and whether they are a workspace admin (webhooks need it);
  2. `teams`         the exact query LinearSink sends; the team keys and state types;
  3. `issueLabels`   the exact query LinearSink sends; the six category labels;
  4. `issueCreate`   through `LinearSink.create` with a ticket UUID as the issue `id` (is it accepted?);
  5. `issue`         the exact recovery query LinearSink sends, by that id;
  6. `issueUpdate`   through `LinearSink.update_status` (in_progress -> `started`) and `close`
                     (-> `completed`), each read back with `issue`;
  7. `issueArchive`  archives every issue this run created (also when a step fails).
Issues are titled "[smoke] ..." and carry a demo banner; CDP-1 and every other issue are left alone.
No webhook is created (Render is not deployed yet).

    python scripts/smoke_linear.py --env-file C:\\path\\to\\.env --yes
    ->  Linear OK team=CDP states=6 labels=6 admin=True id_input=accepted issue=CDP-2 archived=1

The key (LINEAR_API_KEY) is read from `--env-file` (default: the repo `.env`) or the environment, used
only in the Authorization header, and never printed or logged.

Exit codes: 0 every check passed; 1 a check failed (named in the output); 2 refused (no --yes or no key).
"""

from __future__ import annotations

import argparse
import sys
import uuid
from collections.abc import Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from campuspulse_ai.adapters.integrations import linear as linear_mod
from campuspulse_ai.adapters.integrations.linear import LinearMapping, LinearSink
from campuspulse_ai.config.settings import Settings
from campuspulse_ai.domain.entities import Ticket
from campuspulse_ai.domain.errors import SinkError
from campuspulse_ai.domain.labels import Category, Priority
from campuspulse_ai.domain.values import TicketStatus

ROOT = Path(__file__).resolve().parents[1]
TZ = "Asia/Amman"
EXIT_OK, EXIT_FAILED, EXIT_REFUSED = 0, 1, 2
TITLE = "[smoke] CampusPulse integration check (safe to ignore, archived by the script)"
BODY = "Smoke test of the CampusPulse Linear sink (P4.0). Fictional data; this issue is archived at once."

_VIEWER = "query CampusPulseViewer { viewer { id admin } }"
_ISSUE_STATE = (
    "query CampusPulseIssueState($id: String!) { issue(id: $id) { id identifier priority state { type } } }"
)
_ARCHIVE = "mutation CampusPulseIssueArchive($id: String!) { issueArchive(id: $id) { success } }"


class AmmanClock:
    def now(self) -> datetime:
        return datetime.now(ZoneInfo(TZ))


class Run:
    """One live run: a raw GraphQL helper (same endpoint and header as the sink) and the results."""

    def __init__(self, key: str, mapping: LinearMapping, http: httpx.Client) -> None:
        self._key = key
        self._mapping = mapping
        self._http = http
        self.results: dict[str, str] = {}
        self.created: list[str] = []

    def gql(self, query: str, variables: Mapping[str, object] | None = None) -> dict[str, Any]:
        resp = self._http.post(
            self._mapping.api_url,
            json={"query": query, "variables": dict(variables or {})},
            headers={"Authorization": self._key, "Content-Type": "application/json"},
            timeout=self._mapping.timeout_s,
        )
        body = resp.json() if resp.content else {}
        if resp.status_code >= 400 or body.get("errors"):
            errors = body.get("errors") or [{}]
            raise RuntimeError(f"HTTP {resp.status_code}: {errors[0].get('message', 'no message')}")
        data = body.get("data")
        if not isinstance(data, dict):
            raise RuntimeError("no data in the response")
        return data

    def check(self, name: str, ok: bool, detail: str) -> bool:
        self.results[name] = ("verified" if ok else "FAILED") + (f" ({detail})" if detail else "")
        print(f"{name:<14} {self.results[name]}")
        return ok


def smoke_ticket(office: str) -> Ticket:
    now = AmmanClock().now()
    return Ticket(
        id=str(uuid.uuid4()),
        request_id=str(uuid.uuid4()),
        incident_id=None,
        office=office,
        category=Category.IT_SUPPORT,
        priority=Priority.LOW,
        status=TicketStatus.OPEN,
        provisional=False,
        sla_due_at=now + timedelta(days=14),
        title=TITLE,
        body=BODY,
        tags=("smoke-test",),
    )


def run_checks(run: Run, sink: LinearSink, mapping: LinearMapping) -> bool:
    viewer = run.gql(_VIEWER)["viewer"]
    run.check("viewer", bool(viewer.get("id")), f"admin={viewer.get('admin')}")

    teams = run.gql(linear_mod._TEAMS)["teams"]["nodes"]
    team = next((t for t in teams if t.get("key") == mapping.default_team), None)
    states = sorted({s["type"] for s in team["states"]["nodes"]}) if team else []
    needed = {t for t in mapping.state_type_by_status.values() if t}
    ok = team is not None and needed <= set(states)
    if not run.check("teams", ok, f"team={mapping.default_team} state types={','.join(states)}"):
        return False

    labels = {n["name"].casefold() for n in run.gql(linear_mod._LABELS)["issueLabels"]["nodes"]}
    wanted = {v.casefold() for v in mapping.label_by_category.values()}
    run.check("issueLabels", wanted <= labels, f"{len(wanted & labels)}/{len(wanted)} category labels")

    ticket = smoke_ticket("it")
    try:
        link = sink.create(ticket)
    except SinkError as exc:
        run.check("issueCreate", False, str(exc))
        return False
    run.created.append(link.external_id)
    run.check("issueCreate", True, f"url={link.url}")
    run.check("issueCreate.id", link.external_id == ticket.id, "the ticket UUID became the issue id")

    issue = run.gql(linear_mod._ISSUE, {"id": ticket.id})["issue"]
    run.check("issue", issue.get("id") == link.external_id, f"{issue.get('identifier')} looked up by id")
    ticket.links = [link]

    ticket.status = TicketStatus.IN_PROGRESS
    sink.update_status(ticket)
    state = run.gql(_ISSUE_STATE, {"id": link.external_id})["issue"]
    run.check("issueUpdate", state["state"]["type"] == "started", f"state={state['state']['type']}")
    sink.close(ticket)
    state = run.gql(_ISSUE_STATE, {"id": link.external_id})["issue"]
    expected_priority = mapping.priority_for(ticket.priority)
    run.check(
        "issueUpdate.close",
        state["state"]["type"] == "completed" and state["priority"] == expected_priority,
        f"state={state['state']['type']} priority={state['priority']}",
    )
    return all(v.startswith("verified") for v in run.results.values())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env", help="file holding LINEAR_API_KEY")
    parser.add_argument("--yes", action="store_true", help="really call Linear (creates and archives issues)")
    args = parser.parse_args(argv)

    settings = Settings(_env_file=args.env_file)  # type: ignore[call-arg]
    if settings.linear_api_key is None or not settings.linear_api_key.get_secret_value():
        print(f"refused: LINEAR_API_KEY is not set (looked in the environment and {args.env_file})")
        return EXIT_REFUSED
    if not args.yes:
        print("refused: pass --yes to create (and archive) a smoke issue in the real workspace")
        return EXIT_REFUSED

    mapping = LinearMapping.load(ROOT / "config" / "integrations.yaml")
    secret = settings.linear_api_key
    with httpx.Client(timeout=mapping.timeout_s) as http:
        run = Run(secret.get_secret_value(), mapping, http)
        sink = LinearSink(secret, secret, mapping, http, AmmanClock())
        ok = False
        try:
            ok = run_checks(run, sink, mapping)
        except (RuntimeError, SinkError, httpx.HTTPError, KeyError, TypeError) as exc:
            print(f"error          {type(exc).__name__}: {exc}")
        finally:
            archived = 0
            for issue_id in run.created:
                try:
                    archived += bool(run.gql(_ARCHIVE, {"id": issue_id})["issueArchive"]["success"])
                except (RuntimeError, httpx.HTTPError, KeyError) as exc:
                    print(f"archive        FAILED for {issue_id}: {exc}")
            run.check("issueArchive", archived == len(run.created), f"{archived}/{len(run.created)} archived")
    ok = ok and archived == len(run.created)
    print(
        f"Linear {'OK' if ok else 'FAILED'} team={mapping.default_team} "
        f"checks={sum(v.startswith('verified') for v in run.results.values())}/{len(run.results)} "
        f"archived={archived} webhook=not-created"
    )
    return EXIT_OK if ok else EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
