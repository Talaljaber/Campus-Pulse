import type { Clarification, CounterfactualView, TriageResponse } from "@/lib/ai/types";

/** Why a call failed, as the UI needs to say it (the dictionary key is `chat.error<Kind>`). */
export type ChatErrorKind = "generic" | "waking" | "session" | "nothingToAnswer";

/** A live update from the `notifications` table, reduced to what the thread prints. */
export type NoticeData =
  | { type: "ticket_status"; title: string; status: string }
  | { type: "message"; message: string }
  /** UD-13, for staff: a review item landed in the advisor's own queue (`assigned`) or an office queue. */
  | { type: "review_assigned"; assigned: boolean }
  /** UD-13, for staff: a ticket was forwarded to the office from another one. */
  | { type: "ticket_forwarded"; title: string; fromOffice: string }
  | { type: "generic" };

/** One entry of the conversation. `id` is local and stable, used as the React key. */
export type ChatItem =
  | { id: string; role: "student"; text: string }
  /** `text` is the request text the result answers, so top words can be highlighted in it. */
  | { id: string; role: "system"; result: TriageResponse; text: string }
  /** `answered` is the chosen option id. */
  | { id: string; role: "clarify"; requestId: string; q: Clarification; answered?: string }
  | { id: string; role: "notice"; notice: NoticeData }
  | { id: string; role: "error"; kind: ChatErrorKind };

/** Everything the page keeps: the thread, the live counterfactual answers, and the busy flag. */
export interface ChatState {
  items: ChatItem[];
  /** Latest counterfactual answer per `request_id`. */
  counterfactuals: Record<string, CounterfactualView>;
  busy: boolean;
}

export const INITIAL_CHAT: ChatState = { items: [], counterfactuals: {}, busy: false };
