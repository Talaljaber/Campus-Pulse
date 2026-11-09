import type { AgentMessage, AgentState } from "./agentReducer";

/**
 * Keeps the ask-page conversation across a page reload: the visible part of the state is written to
 * localStorage under one key per signed-in alias, and read back when the page opens.
 *
 * - It lasts 24 hours from the last change, then it is dropped.
 * - Sign-out removes every saved conversation (see {@link clearSavedChats}), so a shared computer does
 *   not show the previous person's chat.
 * - A pending proposal whose token has expired is dropped on load, so no dead "Yes, send it" comes back.
 * - Storage can be missing or throw (private window, blocked site data); then nothing is saved.
 */

export const CHAT_TTL_MS = 24 * 60 * 60 * 1000;
/** Only the latest messages are kept; the service reads at most 20 anyway. */
export const MAX_SAVED_MESSAGES = 60;
const PREFIX = "cp.chat.v1:";

type Saved = Pick<AgentState, "messages" | "proposal" | "correction" | "withdraw" | "asked" | "draft">;
interface Envelope {
  savedAt: number;
  state: Saved;
}

export function chatKey(alias: string): string {
  return `${PREFIX}${alias}`;
}

function storage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

/** The epoch-seconds `exp` inside a proposal token (`base64url(json).signature`), or null if unreadable. */
export function tokenExp(token: string): number | null {
  try {
    const payload = token.split(".")[0] ?? "";
    const b64 = payload.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(payload.length / 4) * 4, "=");
    const exp = (JSON.parse(atob(b64)) as { exp?: unknown }).exp;
    return typeof exp === "number" ? exp : null;
  } catch {
    return null;
  }
}

/** Writes the conversation, or removes the key when there is nothing worth keeping. */
export function saveChat(alias: string, state: AgentState, now: number = Date.now(), store: Storage | null = storage()): void {
  if (!store) return;
  try {
    if (state.messages.length === 0 && !state.proposal && !state.withdraw) {
      store.removeItem(chatKey(alias));
      return;
    }
    const saved: Saved = {
      messages: state.messages.slice(-MAX_SAVED_MESSAGES),
      proposal: state.proposal,
      correction: state.correction,
      withdraw: state.withdraw,
      asked: state.asked,
      draft: state.draft,
    };
    store.setItem(chatKey(alias), JSON.stringify({ savedAt: now, state: saved } satisfies Envelope));
  } catch {
    // full or blocked storage: the chat still works, it just is not kept
  }
}

function isMessage(m: unknown): m is AgentMessage {
  if (typeof m !== "object" || m === null) return false;
  const r = m as Record<string, unknown>;
  return typeof r.id === "string" && (r.role === "user" || r.role === "assistant") && typeof r.content === "string" && typeof r.kind === "string";
}

/** Reads the saved conversation for `alias`; null when there is none, it is older than 24 hours, or it is unreadable. */
export function loadChat(alias: string, now: number = Date.now(), store: Storage | null = storage()): Saved | null {
  if (!store) return null;
  try {
    const raw = store.getItem(chatKey(alias));
    if (!raw) return null;
    const env = JSON.parse(raw) as Partial<Envelope>;
    const s = env.state;
    if (typeof env.savedAt !== "number" || now - env.savedAt > CHAT_TTL_MS || !s || !Array.isArray(s.messages) || !s.messages.every(isMessage)) {
      store.removeItem(chatKey(alias));
      return null;
    }
    const exp = s.proposal?.token ? tokenExp(s.proposal.token) : null;
    const live = s.proposal != null && exp !== null && exp * 1000 > now;
    return {
      messages: s.messages,
      proposal: live ? s.proposal : null,
      correction: live ? (s.correction ?? null) : null,
      withdraw: s.withdraw ?? null,
      asked: live && Array.isArray(s.asked) ? s.asked : [],
      draft: typeof s.draft === "string" ? s.draft : "",
    };
  } catch {
    return null;
  }
}

/** Removes every saved conversation in this browser (sign-out). */
export function clearSavedChats(store: Storage | null = storage()): void {
  if (!store) return;
  try {
    const keys: string[] = [];
    for (let i = 0; i < store.length; i++) {
      const k = store.key(i);
      if (k?.startsWith(PREFIX)) keys.push(k);
    }
    keys.forEach((k) => store.removeItem(k));
  } catch {
    // nothing to clear
  }
}
