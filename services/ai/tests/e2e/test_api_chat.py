"""P9.8 over HTTP: chat turn, preview and confirm through the real app (auth, 422s, background follow-up)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from fixtures.api import api_client, auth, services_for
from fixtures.backend_fakes import FakeFAQ, make_core
from fixtures.chat import ScriptedAgent, build_chat, says
from fixtures.lifecycle import ALIAS

from campuspulse_ai.application.use_cases.chat_ports import AgentReply
from campuspulse_ai.domain.journey import TicketHint, ticket_number
from campuspulse_ai.domain.values import FAQHit

TEXT = "The Wi-Fi in building M is down"
STUDENT = auth("student", ALIAS)


def chat_api(agent: ScriptedAgent | None = None, **kw: Any) -> tuple[TestClient, Any]:
    t = build_chat(agent=agent, **kw)
    return api_client(t.c, services=services_for(t.c, lifecycle=t.h.lifecycle, chat=t.uc)), t


def test_turn_proposes_and_confirm_opens_a_ticket_with_its_follow_up() -> None:
    agent = ScriptedAgent(
        replies=[says("x", "request")], phrase_text=lambda f: f"I can send this to {f.department}."
    )
    client, t = chat_api(agent)
    r = client.post("/v1/chat/turn", json={"messages": [{"role": "user", "content": TEXT}]}, headers=STUDENT)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "agent" and body["ticket_id"] is None and body["proposal"]["office"] == "it"
    assert t.tickets() == []
    done = client.post(
        "/v1/chat/confirm", json={"proposal_token": body["proposal"]["token"]}, headers=STUDENT
    )
    assert done.status_code == 200, done.text
    out = done.json()
    [ticket] = t.tickets()
    assert out["ticket_id"] == ticket["id"] and out["hint_applied"] is False
    assert out["triage"]["action"]["type"] == "ticket"
    # the background task ran after the response: the thread's created row and the received emails
    assert [a.kind for a in t.h.journey.activity_for(ticket["id"])] == ["created"]
    assert t.h.mail.sent


def test_confirming_the_same_token_twice_returns_the_same_ticket_and_opens_one() -> None:
    # The durable claim store replays a completed confirm (a double tap or a network retry), so the
    # second call gets the stored result instead of an error, and no second ticket is opened.
    client, t = chat_api()
    token = client.post("/v1/chat/preview", json={"text": TEXT}, headers=STUDENT).json()["token"]
    first = client.post("/v1/chat/confirm", json={"proposal_token": token}, headers=STUDENT)
    second = client.post("/v1/chat/confirm", json={"proposal_token": token}, headers=STUDENT)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json()["ticket_id"] == first.json()["ticket_id"]
    assert len(t.tickets()) == 1


def test_a_yes_in_a_turn_confirms_and_schedules_on_created() -> None:
    agent = ScriptedAgent(
        replies=[says("x", "request"), says("Done.", "confirm")], phrase_text="Shall I? IT Support"
    )
    client, t = chat_api(agent)
    first = client.post(
        "/v1/chat/turn", json={"messages": [{"role": "user", "content": TEXT}]}, headers=STUDENT
    )
    token = first.json()["proposal"]["token"]
    messages = [
        {"role": "user", "content": TEXT},
        {"role": "assistant", "content": "Shall I?", "kind": "proposal"},
        {"role": "user", "content": "yes"},
    ]
    r = client.post("/v1/chat/turn", json={"messages": messages, "proposal_token": token}, headers=STUDENT)
    body = r.json()
    [ticket] = t.tickets()
    assert body["ticket_id"] == ticket["id"] and body["clear_proposal"] is True
    assert body["reply"].startswith("Request recorded: #")
    assert [a.kind for a in t.h.journey.activity_for(ticket["id"])] == ["created"]


def test_bad_tokens_are_422_and_create_nothing() -> None:
    client, t = chat_api()
    token = client.post("/v1/chat/preview", json={"text": TEXT}, headers=STUDENT).json()["token"]
    payload, signature = token.split(".")
    other = client.post(
        "/v1/chat/confirm", json={"proposal_token": token}, headers=auth("student", "demo-18")
    )
    forged = client.post(
        "/v1/chat/confirm", json={"proposal_token": f"{payload}.{'0' * 64}"}, headers=STUDENT
    )
    t.c.clock.at += timedelta(minutes=31)
    expired = client.post("/v1/chat/confirm", json={"proposal_token": token}, headers=STUDENT)
    for r in (other, forged, expired):
        assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_input", r.text
    assert t.tickets() == []


def test_a_past_correction_reroutes_the_ticket_before_the_created_follow_up() -> None:
    client, t = chat_api()
    t.h.journey.add_hint(
        TicketHint(
            kind="forward",
            request_text="p",
            corrected_category="Finance",
            corrected_priority="high",
            embedding=(1.0, 0.0, 0.0),
        )  # fmt: skip
    )
    proposal = client.post("/v1/chat/preview", json={"text": TEXT}, headers=STUDENT).json()
    assert (proposal["office"], proposal["priority"], proposal["hint"]["category"]) == (
        "finance",
        "high",
        "Finance",
    )
    done = client.post("/v1/chat/confirm", json={"proposal_token": proposal["token"]}, headers=STUDENT).json()
    [ticket] = t.tickets()
    assert done["hint_applied"] is True and (ticket["office"], ticket["priority"]) == ("finance", "high")
    kinds = [(a.kind, a.body) for a in t.h.journey.activity_for(ticket["id"])]
    assert kinds[0] == ("forward", "past correction") and kinds[1][0] == "created"


def test_roles_and_wiring() -> None:
    client, _ = chat_api()
    body = {"text": TEXT}
    assert (
        client.post("/v1/chat/preview", json=body, headers=auth()).status_code == 403
    )  # the bare service token
    assert (
        client.post("/v1/chat/preview", json=body, headers=auth("staff", "staff-it", "it")).status_code == 200
    )
    assert client.post("/v1/chat/preview", json=body, headers=auth("admin", "admin")).status_code == 200
    assert client.post("/v1/chat/preview", json=body, headers={}).status_code == 401
    off = api_client()
    r = off.post("/v1/chat/preview", json=body, headers=STUDENT)
    assert r.status_code == 501 and r.json()["error"]["code"] == "not_implemented"


def test_turn_without_an_llm_is_fallback_and_validates_the_conversation() -> None:
    client, t = chat_api(agent=None)
    ok = client.post("/v1/chat/turn", json={"messages": [{"role": "user", "content": "hi"}]}, headers=STUDENT)
    assert ok.json()["mode"] == "fallback" and t.tickets() == []
    ends_with_assistant = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    assert (
        client.post("/v1/chat/turn", json={"messages": ends_with_assistant}, headers=STUDENT).status_code
        == 422
    )
    assert client.post("/v1/chat/turn", json={"messages": []}, headers=STUDENT).status_code == 422
    too_long = [{"role": "user", "content": "x"}] * 21
    assert client.post("/v1/chat/turn", json={"messages": too_long}, headers=STUDENT).status_code == 422
    assert client.post("/v1/chat/turn", json={"messages": [{"role": "user", "content": "x" * 2001}]},
                       headers=STUDENT).status_code == 422  # fmt: skip


def test_triage_route_never_honours_chat_confirmed() -> None:
    hit = FAQHit(
        "f1", "How do I reset my password?", "Use the self-service page.", "https://x.invalid", True, 1.0
    )
    client, t = chat_api(faq=FakeFAQ(hits=[hit]))
    t.core.add("how to reset my password", make_core({"IT Support": 0.9}, {"low": 0.9}))
    r = client.post(
        "/v1/triage", json={"text": "how to reset my password", "chat_confirmed": True}, headers=STUDENT
    )
    assert r.status_code == 200 and r.json()["action"]["type"] == "faq_answer" and t.tickets() == []


def test_a_correction_confirmed_with_replace_closes_the_old_ticket_over_http() -> None:
    """P10.18: the route passes `replace` through; `closed_ticket` is the old ticket as a closed card."""
    agent = ScriptedAgent(phrase_text="I can send this to IT Support.")
    client, t = chat_api(agent)
    wrong = "The projector in room H302 is broken"
    old = client.post("/v1/chat/preview", json={"text": wrong}, headers=STUDENT).json()["token"]
    first = client.post("/v1/chat/confirm", json={"proposal_token": old}, headers=STUDENT)
    old_id = first.json()["ticket_id"]
    right = wrong.replace("H302", "H203")
    refs = (ticket_number(old_id),)
    agent.replies.append(AgentReply("x", "correct", ticket_refs=refs, corrected_text=right))
    turn = client.post(
        "/v1/chat/turn", json={"messages": [{"role": "user", "content": "I meant H203"}]}, headers=STUDENT
    ).json()
    assert turn["correction"]["ticket"]["ticket_id"] == old_id and turn["proposal"]["token"]
    replace = {"proposal_token": turn["proposal"]["token"], "replace": True}
    done = client.post("/v1/chat/confirm", json=replace, headers=STUDENT)
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["closed_ticket"]["ticket_id"] == old_id and body["closed_ticket"]["status"] == "closed"
    statuses = {row["id"]: row["status"] for row in t.tickets()}
    assert statuses == {old_id: "closed", body["ticket_id"]: "new"}
