import type { AiFail } from "@/lib/ai/result";
import type { TriageResponse } from "@/lib/ai/types";
import type { AgentKind, AgentMode, AgentRole, ChatConfirmResponse, ChatTurnResponse, ProposalOut } from "./agentTypes";

export type AgentErrorKind = "generic" | "waking" | "session" | "expired";

/** One entry of the conversation. `ticket` entries carry the recorded request and the proposal it came from. */
export interface AgentMessage {
  id: string;
  role: AgentRole;
  kind: AgentKind;
  content: string;
  ticketId?: string | null;
  triage?: TriageResponse | null;
  proposal?: ProposalOut | null;
}

export interface AgentState {
  messages: AgentMessage[];
  proposal: ProposalOut | null;
  mode: AgentMode;
  busy: boolean;
  error: AgentErrorKind | null;
  /** Clarifying question ids already asked for the current request. */
  asked: string[];
  /** The text the student last sent: pre-fills the fallback form when the assistant fails. */
  draft: string;
}

export const INITIAL_AGENT: AgentState = { messages: [], proposal: null, mode: "llm", busy: false, error: null, asked: [], draft: "" };

export type AgentAction =
  | { type: "sent"; id: string; text: string }
  | { type: "turn"; id: string; res: ChatTurnResponse }
  | { type: "turnFailed"; error: AgentErrorKind; fallback: boolean }
  | { type: "busy" }
  | { type: "previewed"; proposal: ProposalOut; question?: string }
  | { type: "confirmed"; id: string; res: ChatConfirmResponse; text: string }
  | { type: "failed"; error: AgentErrorKind; clearProposal?: boolean }
  | { type: "declined"; id: string; text: string };

/** Maps a failed call to the message kind. 422 means the proposal token is no longer valid. */
export function agentErrorKind(fail: AiFail): AgentErrorKind {
  if (fail.status === 401 || fail.code === "unauthenticated") return "session";
  if (fail.status === 422) return "expired";
  if (fail.waking) return "waking";
  return "generic";
}

const isDistress = (t: TriageResponse | null | undefined) => t?.status === "distress";

export function agentReducer(state: AgentState, action: AgentAction): AgentState {
  switch (action.type) {
    case "sent":
      return {
        ...state,
        busy: true,
        error: null,
        draft: action.text,
        messages: [...state.messages, { id: action.id, role: "user", kind: "text", content: action.text }],
      };
    case "busy":
      return { ...state, busy: true, error: null };
    case "turn": {
      const { res } = action;
      const messages = [...state.messages];
      let proposal = res.clear_proposal ? null : state.proposal;
      let asked = state.asked;
      if (res.triage && (isDistress(res.triage) || res.ticket_id)) {
        messages.push({
          id: action.id,
          role: "assistant",
          kind: res.ticket_id && !isDistress(res.triage) ? "ticket" : "text",
          content: res.reply,
          ticketId: res.ticket_id,
          triage: res.triage,
          proposal: res.ticket_id ? state.proposal : null,
        });
        proposal = null;
        asked = [];
      } else {
        if (res.proposal) proposal = res.proposal;
        if (res.reply.trim()) {
          messages.push({ id: action.id, role: "assistant", kind: res.proposal ? "proposal" : "text", content: res.reply });
        }
        if (res.clear_proposal) asked = [];
      }
      return { ...state, messages, proposal, asked, mode: res.mode, busy: false, error: null };
    }
    case "turnFailed":
      return {
        ...state,
        busy: false,
        error: action.fallback ? null : action.error,
        mode: action.fallback ? "fallback" : state.mode,
      };
    case "previewed":
      return {
        ...state,
        busy: false,
        error: null,
        proposal: action.proposal,
        asked: action.question && !state.asked.includes(action.question) ? [...state.asked, action.question] : state.asked,
      };
    case "confirmed":
      return {
        ...state,
        busy: false,
        error: null,
        proposal: null,
        asked: [],
        messages: [
          ...state.messages,
          {
            id: action.id,
            role: "assistant",
            kind: isDistress(action.res.triage) ? "text" : "ticket",
            content: action.text,
            ticketId: action.res.ticket_id,
            triage: action.res.triage,
            proposal: state.proposal,
          },
        ],
      };
    case "failed":
      return { ...state, busy: false, error: action.error, proposal: action.clearProposal ? null : state.proposal };
    case "declined":
      return {
        ...state,
        proposal: null,
        asked: [],
        error: null,
        messages: [...state.messages, { id: action.id, role: "assistant", kind: "text", content: action.text }],
      };
  }
}
