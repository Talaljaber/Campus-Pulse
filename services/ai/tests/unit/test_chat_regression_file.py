"""P9.8: the scripted conversations are well-formed and the script's checker works (no key, no network)."""

from __future__ import annotations

import importlib.util
import sys

from campuspulse_ai.config.paths import REPO_ROOT

SPEC = importlib.util.spec_from_file_location(
    "run_chat_regression", REPO_ROOT / "scripts" / "run_chat_regression.py"
)
assert SPEC is not None and SPEC.loader is not None
script = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = script
SPEC.loader.exec_module(script)


def test_the_conversation_file_covers_the_required_situations() -> None:
    conversations = script.load_conversations()
    ids = {c["id"] for c in conversations}
    assert len(conversations) >= 10 and len(ids) == len(conversations)
    assert {c["lang"] for c in conversations} == {"en", "ar", "arabizi"}
    assert {c.get("role", "student") for c in conversations} == {"student", "staff"}
    for needle in ("injection", "announcement", "vague", "frustrated", "staff", "distress", "decline"):
        assert any(needle in i for i in ids), needle
    for conv in conversations:
        assert conv["steps"], conv["id"]
        for step in conv["steps"]:
            assert step["say"].strip()
            assert set(step.get("expect", {})) <= script.EXPECT_KEYS, (conv["id"], step["expect"])


def reply(text: str, **fields: object) -> dict[str, object]:
    return {
        "reply": text,
        "proposal": None,
        "ticket_id": None,
        "triage": None,
        "clear_proposal": False,
        **fields,
    }


def test_the_checker_flags_each_kind_of_failure() -> None:
    def failures(expect: dict[str, object], response: dict[str, object]) -> list[str]:
        return script.check(expect, response, first_name="Lina", first_step=True)

    proposal = {"token": "t", "office": "it"}
    assert failures({"proposal": True, "office": "it"}, reply("Hi Lina, shall I?", proposal=proposal)) == []
    assert failures({"proposal": True}, reply("Hi")) == ["proposal=True"]
    assert failures({"ticket": False}, reply("Hi", ticket_id="x")) == ["ticket=False"]
    assert failures({"not_office": "finance"}, reply("Hi", proposal={"token": "t", "office": "finance"}))
    assert failures({"no_banned": True}, reply("We contacted IT")) == ["no_banned=True"]
    assert failures({"reply_lang": "ar"}, reply("hello")) == ["reply_lang='ar'"]
    assert failures({"reply_lang": "ar"}, reply("أهلاً وسهلاً")) == []
    assert failures({"asks_question": True}, reply("Which account?")) == []
    assert failures({"no_student_id": True}, reply("What is your student ID?")) == ["no_student_id=True"]
    assert failures({"greets_by_name": True}, reply("Hello there")) == ["greets_by_name=True"]
    assert failures({"distress": True}, reply("x", triage={"status": "distress"})) == []
    assert failures({"reply_contains_any": ["maintenance"]}, reply("A Maintenance notice")) == []
