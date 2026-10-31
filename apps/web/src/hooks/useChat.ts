"use client";

import { useCallback, useEffect, useReducer, useRef } from "react";
import { chatReducer } from "@/lib/chat/reducer";
import {
  answerClarification,
  chatErrorKind,
  fetchCounterfactual,
  submitTriage,
  type InputMode,
} from "@/lib/chat/service";
import { INITIAL_CHAT, type ChatItem, type NoticeData } from "@/lib/chat/types";

/** The text of the student message a clarification question belongs to (the nearest one before it). */
export function requestTextFor(items: readonly ChatItem[], itemId: string): string {
  const at = items.findIndex((i) => i.id === itemId);
  for (let k = at - 1; k >= 0; k--) {
    const item = items[k];
    if (item?.role === "student") return item.text;
  }
  return "";
}

/**
 * The student chat: sends a request, handles the clarifying question, fetches
 * counterfactuals and accepts live notices. It owns the conversation state and nothing
 * else; the components get plain props. (Plan names `useTriage`, `useClarify` and
 * `useCounterfactual` are one hook here because they share the thread.)
 */
export function useChat() {
  const [state, dispatch] = useReducer(chatReducer, INITIAL_CHAT);
  const stateRef = useRef(state);
  const seq = useRef(0);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  const nextId = useCallback((prefix: string) => `${prefix}${++seq.current}`, []);

  const send = useCallback(
    async (rawText: string, mode: InputMode, buildingId: string | null) => {
      const text = rawText.trim();
      if (!text || stateRef.current.busy) return;
      dispatch({ type: "sent", id: nextId("s"), text });
      // The reducer has not run yet inside this tick, so lock against a double submit here too.
      stateRef.current = { ...stateRef.current, busy: true };
      const res = await submitTriage(text, mode, buildingId);
      if (res.ok) dispatch({ type: "result", id: nextId("r"), text, result: res.data });
      else dispatch({ type: "failed", id: nextId("e"), kind: chatErrorKind(res, "triage") });
    },
    [nextId],
  );

  const pick = useCallback(
    async (itemId: string, optionId: string) => {
      const items = stateRef.current.items;
      const item = items.find((i) => i.id === itemId);
      if (!item || item.role !== "clarify" || item.answered !== undefined || stateRef.current.busy) return;
      const text = requestTextFor(items, itemId);
      dispatch({ type: "picked", itemId, optionId });
      stateRef.current = { ...stateRef.current, busy: true };
      const res = await answerClarification(item.requestId, item.q.question_id, optionId);
      if (res.ok) {
        dispatch({ type: "result", id: nextId("r"), text, result: res.data, answers: { itemId, optionId } });
      } else {
        dispatch({ type: "failed", id: nextId("e"), kind: chatErrorKind(res, "clarify"), reopen: itemId });
      }
    },
    [nextId],
  );

  const counterfactual = useCallback(
    async (requestId: string, token: string) => {
      const res = await fetchCounterfactual(requestId, token);
      if (res.ok) dispatch({ type: "counterfactual", view: res.data });
      else dispatch({ type: "failed", id: nextId("e"), kind: chatErrorKind(res), background: true });
    },
    [nextId],
  );

  const notice = useCallback(
    (data: NoticeData) => dispatch({ type: "notice", id: nextId("n"), notice: data }),
    [nextId],
  );

  return { ...state, send, pick, counterfactual, notice };
}
