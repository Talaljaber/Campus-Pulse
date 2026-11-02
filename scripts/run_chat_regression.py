"""Chat agent regression (P9.8): replay `services/ai/tests/chat/conversations.yaml` against the real stack.

Needs a real `OPENROUTER_API_KEY` (the pinned chat model of `config/chat_agent.yaml` is called, temperature
0, responses cached) and the frozen model artifacts. NOT part of CI. Without a key it prints "not run" and
exits 2.
The stack is the production wiring (`wire_online`) over in-memory adapters, so nothing is written to Supabase
and no email can leave (no email channel is wired). Writes `reports/chat_regression.json`.

    python scripts/run_chat_regression.py [--only en_normal_request] [--out reports/chat_regression.json]

Exit codes: 0 all conversations passed, 1 at least one expectation failed, 2 not run (no key or no model).
The key is read from the environment or `.env` by `Settings` and is never printed or written.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path
from typing import Any

import yaml

from campuspulse_ai.config.paths import REPO_ROOT
from campuspulse_ai.config.settings import Settings

CONVERSATIONS = REPO_ROOT / "services" / "ai" / "tests" / "chat" / "conversations.yaml"
DEFAULT_OUT = REPO_ROOT / "reports" / "chat_regression.json"
BANNED = ("contacted", "notified", "confidence", "conformal", "probability", "تم إبلاغ", "تم التواصل")
EXPECT_KEYS = frozenset({
    "proposal", "ticket", "clear_proposal", "office", "not_office", "distress", "reply_lang", "asks_question",
    "reply_contains_any", "no_banned", "no_student_id", "greets_by_name",
})  # fmt: skip
ARABIC = re.compile("[؀-ۿ]")
STAFF_ALIAS = "staff-it"
STUDENT_ALIAS = "demo-17"
NOT_RUN = 2


def reply_is_arabic(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and sum(1 for c in letters if ARABIC.match(c)) / len(letters) > 0.5  # noqa: PLR2004


def check(
    expect: Mapping[str, Any], response: Mapping[str, Any], *, first_name: str, first_step: bool
) -> list[str]:
    """The failed expectations of one step (pure; `response` is the `ChatTurnResponse` as a dict)."""
    reply = str(response["reply"])
    low = reply.lower()
    proposal = response.get("proposal") or {}
    failures: list[str] = []

    def want(key: str, ok: bool) -> None:
        if key in expect and not ok:
            failures.append(f"{key}={expect[key]!r}")

    want("proposal", bool(proposal.get("token")) == bool(expect.get("proposal")))
    want("ticket", (response.get("ticket_id") is not None) == bool(expect.get("ticket")))
    want("clear_proposal", bool(response.get("clear_proposal")) == bool(expect.get("clear_proposal")))
    want("office", proposal.get("office") == expect.get("office"))
    want("not_office", proposal.get("office") != expect.get("not_office"))
    triage = response.get("triage") or {}
    want("distress", (triage.get("status") == "distress") == bool(expect.get("distress")))
    want("reply_lang", reply_is_arabic(reply) == (expect.get("reply_lang") == "ar"))
    want("asks_question", reply.rstrip().endswith(("?", "؟")) == bool(expect.get("asks_question")))
    want("reply_contains_any", any(str(w).lower() in low for w in expect.get("reply_contains_any", [])))
    want("no_banned", not (expect.get("no_banned") and any(b.lower() in low for b in BANNED)))
    want("no_student_id", not (expect.get("no_student_id") and "student id" in low))
    want(
        "greets_by_name", not (expect.get("greets_by_name") and first_step and first_name.lower() not in low)
    )
    return failures


def load_conversations(path: Path = CONVERSATIONS) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return list(data["conversations"])


def build_services(settings: Settings) -> tuple[Any, Any]:
    """(`ApiServices`, adapters) over in-memory adapters and the real frozen model (no Supabase, no email)."""
    from campuspulse_ai.adapters.integrations.supabase_sink import SupabaseSink
    from campuspulse_ai.adapters.memory.inmemory import InMemoryMemoryStore
    from campuspulse_ai.adapters.notify.inapp import InAppNotifier
    from campuspulse_ai.adapters.store.announcements_inmemory import InMemoryAnnouncementStore
    from campuspulse_ai.adapters.store.inmemory import InMemoryRepository
    from campuspulse_ai.adapters.store.journey_inmemory import InMemoryJourneyStore
    from campuspulse_ai.adapters.vectors.local_numpy import LocalNumpyVectorStore
    from campuspulse_ai.composition import online

    clock = online.SystemClock()
    offline = online.load_offline(settings)
    repo = InMemoryRepository(clock)
    repo.add_profile(STUDENT_ALIAS, "student", display_name="Lina Haddad")
    repo.add_profile(STAFF_ALIAS, "staff", "it", display_name="Omar Saleh")
    adapters = online.OnlineAdapters(
        repo=repo,
        reads=repo,
        marks=repo,
        vectors=LocalNumpyVectorStore(offline.config.encoder.dim, collections=("requests", "faq")),
        memory=InMemoryMemoryStore(),
        sinks=(SupabaseSink(repo),),
        channels={"in_app": InAppNotifier(repo)},
        vector_store="local",
        journey=InMemoryJourneyStore(repo),
        announcements=InMemoryAnnouncementStore(),
    )
    return online.wire_online(settings, offline, adapters, clock), adapters


def run_conversation(conv: Mapping[str, Any], services: Any, adapters: Any) -> dict[str, Any]:
    from campuspulse_ai.application import dto
    from campuspulse_ai.domain.announcements import Announcement
    from campuspulse_ai.frameworks.auth import Principal

    role = str(conv.get("role", "student"))
    alias = str(conv.get("alias", STAFF_ALIAS if role == "staff" else STUDENT_ALIAS))
    caller = Principal(user_id=None, role=role, alias=alias, office="it" if role == "staff" else None)  # type: ignore[arg-type]
    clock = services.clock
    for note in conv.get("announcements", []):
        adapters.announcements.save_announcement(
            Announcement(
                "", None, note["kind"], note["title"], note["body"], clock.now() - timedelta(hours=1)
            )
        )
    first_name = "Omar" if role == "staff" else "Lina"
    history: list[dto.ChatMessage] = []
    token: str | None = None
    steps: list[dict[str, Any]] = []
    for index, step in enumerate(conv["steps"]):
        history.append(dto.ChatMessage(role="user", content=step["say"]))
        out = services.chat.turn(dto.ChatTurnRequest(messages=history, proposal_token=token), caller)
        data = json.loads(out.model_dump_json())
        failures = check(step.get("expect", {}), data, first_name=first_name, first_step=index == 0)
        kind = "proposal" if out.proposal is not None else "ticket" if out.ticket_id else "text"
        history.append(dto.ChatMessage(role="assistant", content=out.reply, kind=kind))  # type: ignore[arg-type]
        token = out.proposal.token if out.proposal is not None else (None if out.clear_proposal else token)
        steps.append({"say": step["say"], "reply": out.reply, "mode": out.mode, "failures": failures})
    return {
        "id": conv["id"],
        "lang": conv["lang"],
        "passed": not any(s["failures"] for s in steps),
        "steps": steps,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", action="append", default=[], help="conversation id (repeatable)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    settings = Settings()
    if settings.openrouter_api_key is None or not settings.chat_agent_enabled:
        print("not run: OPENROUTER_API_KEY is not set (or CHAT_AGENT_ENABLED=false)")  # noqa: T201
        return NOT_RUN
    conversations = [c for c in load_conversations() if not args.only or c["id"] in args.only]
    results: list[dict[str, Any]] = []
    for conv in conversations:
        services, adapters = build_services(settings)  # a fresh in-memory campus per conversation
        if services.chat is None or not services.chat.llm_enabled:
            print("not run: the chat agent is not wired (needs AI_SERVICE_TOKEN and a key)")  # noqa: T201
            return NOT_RUN
        results.append(run_conversation(conv, services, adapters))
        print(("PASS " if results[-1]["passed"] else "FAIL ") + conv["id"])  # noqa: T201
    args.out.parent.mkdir(parents=True, exist_ok=True)
    pinned = yaml.safe_load((REPO_ROOT / "config" / "chat_agent.yaml").read_text("utf-8"))["model"]
    passed = sum(1 for r in results if r["passed"])
    report = {"model": pinned, "passed": passed, "total": len(results), "conversations": results}
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{report['passed']}/{report['total']} conversations passed -> {args.out}")  # noqa: T201
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
