import type { CounterfactualView, TriageResponse } from "@/lib/ai/types";
import type { ChatErrorKind, ChatItem, ChatState, NoticeData } from "./types";

export type ChatAction =
  /** The student sent a message; the thread shows it and the page is busy. */
  | { type: "sent"; id: string; text: string }
  /** A triage or clarify answer. `answers` is the clarify item it resolves, if any. */
  | { type: "result"; id: string; text: string; result: TriageResponse; answers?: { itemId: string; optionId: string } }
  /** The call failed. A failed clarification re-opens its question. */
  | { type: "failed"; id: string; kind: ChatErrorKind; reopen?: string; background?: boolean }
  /** The student picked a chip; it is marked and the page is busy until the answer arrives. */
  | { type: "picked"; itemId: string; optionId: string }
  | { type: "counterfactual"; view: CounterfactualView }
  | { type: "notice"; id: string; notice: NoticeData };

/**
 * What a triage response adds to the thread:
 * - `needs_clarification`: only the question bubble (the provisional labels are not shown yet);
 * - `out_of_scope` with topic chips: the result card (the rephrase prompt) and the chips;
 * - everything else: the result card.
 */
function itemsFor(id: string, text: string, result: TriageResponse): ChatItem[] {
  const question: ChatItem | null = result.clarification
    ? { id: `${id}-q`, role: "clarify", requestId: result.request_id, q: result.clarification }
    : null;
  if (result.status === "needs_clarification" && question) return [question];
  const card: ChatItem = { id, role: "system", result, text };
  return question ? [card, question] : [card];
}

/** Pure state transition of the chat page. No clock, no randomness: ids come in with the action. */
export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "sent":
      return { ...state, busy: true, items: [...state.items, { id: action.id, role: "student", text: action.text }] };

    case "picked":
      return {
        ...state,
        busy: true,
        items: state.items.map((i) =>
          i.id === action.itemId && i.role === "clarify" ? { ...i, answered: action.optionId } : i,
        ),
      };

    case "result": {
      const items = action.answers
        ? state.items.map((i) =>
            i.id === action.answers!.itemId && i.role === "clarify" ? { ...i, answered: action.answers!.optionId } : i,
          )
        : state.items;
      return { ...state, busy: false, items: [...items, ...itemsFor(action.id, action.text, action.result)] };
    }

    case "failed": {
      const items = state.items.map((i) =>
        i.id === action.reopen && i.role === "clarify" ? { ...i, answered: undefined } : i,
      );
      // `background` failures (a counterfactual click) must not unlock a request that is still in flight.
      return {
        ...state,
        busy: action.background ? state.busy : false,
        items: [...items, { id: action.id, role: "error", kind: action.kind }],
      };
    }

    case "counterfactual":
      return { ...state, counterfactuals: { ...state.counterfactuals, [action.view.request_id]: action.view } };

    case "notice":
      return { ...state, items: [...state.items, { id: action.id, role: "notice", notice: action.notice }] };
  }
}
