import { describe, expect, it } from "vitest";
import { TRIAGE_FIXTURES } from "@/lib/fixtures/api";
import { toWire } from "../agent";
import { agentErrorKind, agentReducer, INITIAL_AGENT, type AgentState } from "../agentReducer";
import type { ChatTurnResponse, ProposalOut } from "../agentTypes";

const P = { token: "t", text: "x", office: "it", question: null } as ProposalOut;
const turn = (o: Partial<ChatTurnResponse>): ChatTurnResponse => ({
  mode: "agent",
  reply: "",
  proposal: null,
  ticket_id: null,
  triage: null,
  clear_proposal: false,
  ...o,
});
const sent = (s: AgentState) => agentReducer(s, { type: "sent", id: "u1", text: "hello" });

describe("agentReducer", () => {
  it("sent adds the message, locks and remembers the draft", () => {
    const s = sent(INITIAL_AGENT);
    expect(s).toMatchObject({ busy: true, draft: "hello", messages: [{ role: "user", content: "hello" }] });
  });

  it("a distress preview adds the supportive text as a distress message and no proposal", () => {
    const distress = { ...P, token: "", question: { question_id: "distress", text: "Be kind to yourself.", options: [] } } as ProposalOut;
    const s = agentReducer(sent(INITIAL_AGENT), { type: "previewed", proposal: distress });
    expect(s.proposal).toBeNull();
    expect(s.messages.at(-1)).toMatchObject({ role: "assistant", content: "Be kind to yourself.", distress: true });
  });

  it("a turn with a proposal keeps it pending and shows the reply", () => {
    const s = agentReducer(sent(INITIAL_AGENT), { type: "turn", id: "a1", res: turn({ reply: "ok", proposal: P }) });
    expect(s.proposal).toBe(P);
    expect(s.busy).toBe(false);
    expect(s.messages.at(-1)).toMatchObject({ role: "assistant", kind: "proposal", content: "ok" });
  });

  it("clear_proposal drops the pending proposal and the asked ids", () => {
    const base = { ...INITIAL_AGENT, proposal: P, asked: ["q1"] };
    const s = agentReducer(sent(base), { type: "turn", id: "a1", res: turn({ reply: "fine", clear_proposal: true }) });
    expect(s.proposal).toBeNull();
    expect(s.asked).toEqual([]);
  });

  it("a turn that created a ticket adds a ticket message that keeps the proposal for 'Why this?'", () => {
    const triage = TRIAGE_FIXTURES.enMemory.response;
    const s = agentReducer(sent({ ...INITIAL_AGENT, proposal: P }), { type: "turn", id: "a1", res: turn({ reply: "r", ticket_id: "tk", triage }) });
    expect(s.proposal).toBeNull();
    expect(s.messages.at(-1)).toMatchObject({ kind: "ticket", ticketId: "tk", proposal: P });
  });

  it("mode comes from the turn; a fallback turn without reply adds no empty bubble", () => {
    const s = agentReducer(sent(INITIAL_AGENT), { type: "turn", id: "a1", res: turn({ mode: "fallback" }) });
    expect(s.mode).toBe("fallback");
    expect(s.messages).toHaveLength(1);
  });

  it("a failed turn with fallback switches mode and shows no error", () => {
    const s = agentReducer(sent(INITIAL_AGENT), { type: "turnFailed", error: "waking", fallback: true });
    expect(s).toMatchObject({ mode: "fallback", error: null, busy: false });
  });

  it("a failed turn without fallback keeps the mode and shows the error", () => {
    const s = agentReducer(sent(INITIAL_AGENT), { type: "turnFailed", error: "generic", fallback: false });
    expect(s).toMatchObject({ mode: "agent", error: "generic" });
  });

  it("previewed stores the proposal and records the answered question once", () => {
    let s = agentReducer({ ...INITIAL_AGENT, busy: true }, { type: "previewed", proposal: P, question: "q1" });
    s = agentReducer(s, { type: "previewed", proposal: P, question: "q1" });
    expect(s).toMatchObject({ proposal: P, asked: ["q1"], busy: false });
  });

  it("confirmed adds the ticket message and clears the proposal", () => {
    const triage = TRIAGE_FIXTURES.enMemory.response;
    const s = agentReducer({ ...INITIAL_AGENT, proposal: P, busy: true }, { type: "confirmed", id: "a1", res: { triage, ticket_id: "tk", hint_applied: false }, text: "done" });
    expect(s.proposal).toBeNull();
    expect(s.messages.at(-1)).toMatchObject({ kind: "ticket", ticketId: "tk", proposal: P });
  });

  it("declined clears the proposal without a request", () => {
    const s = agentReducer({ ...INITIAL_AGENT, proposal: P }, { type: "declined", id: "a1", text: "ok" });
    expect(s.proposal).toBeNull();
  });

  it("failed with clearProposal drops an expired proposal", () => {
    const s = agentReducer({ ...INITIAL_AGENT, proposal: P, busy: true }, { type: "failed", error: "expired", clearProposal: true });
    expect(s).toMatchObject({ proposal: null, error: "expired", busy: false });
  });
});

describe("agentErrorKind and toWire", () => {
  const fail = (status: number, code = "internal_error", waking = false) =>
    ({ ok: false, status, code, error: "", details: null, waking }) as Parameters<typeof agentErrorKind>[0];
  it("maps status codes", () => {
    expect(agentErrorKind(fail(401))).toBe("session");
    expect(agentErrorKind(fail(422))).toBe("expired");
    expect(agentErrorKind(fail(503, "network", true))).toBe("waking");
    expect(agentErrorKind(fail(500))).toBe("generic");
  });
  it("keeps the last 20 messages and cuts long ones at 2000 characters", () => {
    const many = Array.from({ length: 25 }, (_, i) => ({ role: "user" as const, content: `m${i}` }));
    expect(toWire(many)).toHaveLength(20);
    expect(toWire(many)[0]?.content).toBe("m5");
    expect(toWire([{ role: "user", content: "x".repeat(2500) }])[0]?.content).toHaveLength(2000);
  });
});
