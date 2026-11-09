import { beforeEach, describe, expect, it } from "vitest";
import { agentReducer, INITIAL_AGENT, type AgentState } from "../agentReducer";
import type { ProposalOut } from "../agentTypes";
import { CHAT_TTL_MS, chatKey, clearSavedChats, loadChat, MAX_SAVED_MESSAGES, saveChat, tokenExp } from "../persist";

const NOW = Date.UTC(2026, 10, 9, 12, 0, 0);
/** A token shaped like the service's: base64url(json).signature */
const token = (exp: number) =>
  `${btoa(JSON.stringify({ alias: "lina", text: "x", exp })).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")}.sig`;
const proposal = (exp: number) => ({ token: token(exp), text: "wifi", office: "it", question: null }) as ProposalOut;

const chat = (o: Partial<AgentState> = {}): AgentState => ({
  ...INITIAL_AGENT,
  messages: [
    { id: "u1", role: "user", kind: "text", content: "mate we have a wifi issue" },
    { id: "a2", role: "assistant", kind: "text", content: "Which building?", sources: [{ id: "announcement:1", kind: "announcement", title: "Library wifi is down" }] },
  ],
  draft: "mate we have a wifi issue",
  ...o,
});

beforeEach(() => localStorage.clear());

describe("chat persistence", () => {
  it("restores the conversation for the same alias, sources included", () => {
    saveChat("lina", chat(), NOW);
    const back = loadChat("lina", NOW + 60_000);
    expect(back?.messages).toEqual(chat().messages);
    expect(back?.draft).toBe("mate we have a wifi issue");
  });

  it("keeps it per person: another alias sees nothing", () => {
    saveChat("lina", chat(), NOW);
    expect(loadChat("omar", NOW)).toBeNull();
  });

  it("drops it after 24 hours and removes the key", () => {
    saveChat("lina", chat(), NOW);
    expect(loadChat("lina", NOW + CHAT_TTL_MS - 1)).not.toBeNull();
    expect(loadChat("lina", NOW + CHAT_TTL_MS + 1)).toBeNull();
    expect(localStorage.getItem(chatKey("lina"))).toBeNull();
  });

  it("keeps a pending proposal while its token is valid and drops it with its question state once expired", () => {
    const live = chat({ proposal: proposal(NOW / 1000 + 600), asked: ["q_building"] });
    saveChat("lina", live, NOW);
    expect(loadChat("lina", NOW)?.proposal?.text).toBe("wifi");
    expect(loadChat("lina", NOW)?.asked).toEqual(["q_building"]);
    const later = loadChat("lina", NOW + 601_000);
    expect(later?.proposal).toBeNull();
    expect(later?.asked).toEqual([]);
    expect(later?.messages).toHaveLength(2);
  });

  it("drops a proposal whose token cannot be read", () => {
    saveChat("lina", chat({ proposal: { ...proposal(0), token: "not-a-token" } }), NOW);
    expect(loadChat("lina", NOW)?.proposal).toBeNull();
  });

  it("reads exp from a service-shaped token", () => {
    expect(tokenExp(token(1_800_000_000))).toBe(1_800_000_000);
    expect(tokenExp("garbage")).toBeNull();
  });

  it("keeps only the latest messages", () => {
    const many = Array.from({ length: MAX_SAVED_MESSAGES + 10 }, (_, i) => ({ id: `u${i}`, role: "user" as const, kind: "text" as const, content: `m${i}` }));
    saveChat("lina", chat({ messages: many }), NOW);
    const back = loadChat("lina", NOW);
    expect(back?.messages).toHaveLength(MAX_SAVED_MESSAGES);
    expect(back?.messages.at(-1)?.content).toBe(`m${MAX_SAVED_MESSAGES + 9}`);
  });

  it("an empty conversation removes the saved one (New chat)", () => {
    saveChat("lina", chat(), NOW);
    saveChat("lina", INITIAL_AGENT, NOW);
    expect(localStorage.getItem(chatKey("lina"))).toBeNull();
  });

  it("ignores broken or foreign data", () => {
    localStorage.setItem(chatKey("lina"), "{not json");
    expect(loadChat("lina", NOW)).toBeNull();
    localStorage.setItem(chatKey("lina"), JSON.stringify({ savedAt: NOW, state: { messages: [{ id: 1 }] } }));
    expect(loadChat("lina", NOW)).toBeNull();
  });

  it("sign-out clears every saved chat and nothing else", () => {
    saveChat("lina", chat(), NOW);
    saveChat("omar", chat(), NOW);
    localStorage.setItem("cp.lang", "ar");
    clearSavedChats();
    expect(loadChat("lina", NOW)).toBeNull();
    expect(loadChat("omar", NOW)).toBeNull();
    expect(localStorage.getItem("cp.lang")).toBe("ar");
  });

  it("restored fills only an untouched page; reset starts over", () => {
    const saved = { messages: chat().messages, proposal: null, correction: null, withdraw: null, asked: [], draft: "" };
    expect(agentReducer(INITIAL_AGENT, { type: "restored", saved }).messages).toHaveLength(2);
    const started = agentReducer(INITIAL_AGENT, { type: "sent", id: "u9", text: "new" });
    expect(agentReducer(started, { type: "restored", saved })).toBe(started);
    expect(agentReducer(chat(), { type: "reset" })).toEqual(INITIAL_AGENT);
  });
});
