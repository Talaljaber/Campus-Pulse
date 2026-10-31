import { describe, expect, it } from "vitest";
import { COUNTERFACTUAL_FIXTURE, TRIAGE_FIXTURES } from "@/lib/fixtures/api";
import { chatReducer } from "@/lib/chat/reducer";
import { INITIAL_CHAT, type ChatState } from "@/lib/chat/types";

const { arClarification, enOutOfScope, enFaq, arDistress } = TRIAGE_FIXTURES;

const withStudent = (text: string): ChatState => chatReducer(INITIAL_CHAT, { type: "sent", id: "s1", text });

describe("chatReducer", () => {
  it("a sent message shows the bubble and locks the page", () => {
    const s = withStudent("hello");
    expect(s.busy).toBe(true);
    expect(s.items).toEqual([{ id: "s1", role: "student", text: "hello" }]);
  });

  it("needs_clarification adds only the question, not a result card", () => {
    const s = chatReducer(withStudent(arClarification.text), {
      type: "result",
      id: "r1",
      text: arClarification.text,
      result: arClarification.response,
    });
    expect(s.busy).toBe(false);
    expect(s.items.map((i) => i.role)).toEqual(["student", "clarify"]);
    const q = s.items[1];
    expect(q?.role === "clarify" && q.q.options.length).toBeGreaterThanOrEqual(2);
  });

  it("out_of_scope keeps the rephrase card and adds the topic chips", () => {
    const s = chatReducer(withStudent(enOutOfScope.text), {
      type: "result",
      id: "r1",
      text: enOutOfScope.text,
      result: enOutOfScope.response,
    });
    expect(s.items.map((i) => i.role)).toEqual(["student", "system", "clarify"]);
    const q = s.items[2];
    expect(q?.role === "clarify" && q.q.question_id).toBe("topic");
  });

  it("decided and distress add a single card", () => {
    for (const fx of [enFaq, arDistress]) {
      const s = chatReducer(withStudent(fx.text), { type: "result", id: "r", text: fx.text, result: fx.response });
      expect(s.items.map((i) => i.role)).toEqual(["student", "system"]);
    }
  });

  it("picking a chip marks it answered and locks; the answer unlocks and appends the result", () => {
    let s = chatReducer(withStudent("x"), { type: "result", id: "r1", text: "x", result: arClarification.response });
    const clarifyId = s.items[1]!.id;
    s = chatReducer(s, { type: "picked", itemId: clarifyId, optionId: "registration" });
    expect(s.busy).toBe(true);
    expect(s.items[1]).toMatchObject({ answered: "registration" });
    s = chatReducer(s, {
      type: "result",
      id: "r2",
      text: "x",
      result: enFaq.response,
      answers: { itemId: clarifyId, optionId: "registration" },
    });
    expect(s.busy).toBe(false);
    expect(s.items.map((i) => i.role)).toEqual(["student", "clarify", "system"]);
  });

  it("a failed clarification re-opens the question", () => {
    let s = chatReducer(withStudent("x"), { type: "result", id: "r1", text: "x", result: arClarification.response });
    const clarifyId = s.items[1]!.id;
    s = chatReducer(s, { type: "picked", itemId: clarifyId, optionId: "it" });
    s = chatReducer(s, { type: "failed", id: "e1", kind: "waking", reopen: clarifyId });
    expect(s.busy).toBe(false);
    expect(s.items[1]).toMatchObject({ answered: undefined });
    expect(s.items[2]).toEqual({ id: "e1", role: "error", kind: "waking" });
  });

  it("a background failure does not unlock a request that is still running", () => {
    const s = chatReducer(withStudent("x"), { type: "failed", id: "e", kind: "generic", background: true });
    expect(s.busy).toBe(true);
  });

  it("stores the counterfactual by request id and appends notices", () => {
    let s = chatReducer(INITIAL_CHAT, { type: "counterfactual", view: COUNTERFACTUAL_FIXTURE });
    expect(s.counterfactuals[COUNTERFACTUAL_FIXTURE.request_id]).toEqual(COUNTERFACTUAL_FIXTURE);
    s = chatReducer(s, { type: "notice", id: "n1", notice: { type: "generic" } });
    expect(s.items).toEqual([{ id: "n1", role: "notice", notice: { type: "generic" } }]);
    expect(s.busy).toBe(false);
  });
});
