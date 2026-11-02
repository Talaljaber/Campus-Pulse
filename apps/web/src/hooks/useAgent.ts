"use client";

import { useCallback, useEffect, useReducer, useRef } from "react";
import { confirm, preview, sendTurn } from "@/lib/chat/agent";
import { agentErrorKind, agentReducer, INITIAL_AGENT } from "@/lib/chat/agentReducer";

/** Whether a failed turn means "the assistant is not available": the page then shows the plain form. */
function unavailable(fail: { status: number; waking: boolean }): boolean {
  return fail.waking || fail.status >= 500;
}

/**
 * The ask page state: free text goes to `chat/turn`; the fallback form and the question chips use
 * `chat/preview`; "Yes, send it" uses `chat/confirm`. The service decides; nothing is created here.
 * `texts` are the sentences the hook adds to the conversation itself (translated by the page).
 */
export function useAgent(texts: { recorded: string; declined: string }) {
  const [state, dispatch] = useReducer(agentReducer, INITIAL_AGENT);
  const stateRef = useRef(state);
  const seq = useRef(0);
  const textsRef = useRef(texts);

  useEffect(() => {
    stateRef.current = state;
    textsRef.current = texts;
  }, [state, texts]);

  const nextId = useCallback((prefix: string) => `${prefix}${++seq.current}`, []);

  /** Free text. With a pending proposal the token travels along, so "yes" can confirm it. */
  const send = useCallback(
    async (rawText: string) => {
      const text = rawText.trim();
      const cur = stateRef.current;
      if (!text || cur.busy) return;
      const user = { id: nextId("u"), role: "user" as const, kind: "text" as const, content: text };
      dispatch({ type: "sent", id: user.id, text });
      stateRef.current = { ...cur, busy: true, messages: [...cur.messages, user] };
      const res = await sendTurn(stateRef.current.messages, cur.proposal?.token ?? null);
      if (res.ok) dispatch({ type: "turn", id: nextId("a"), res: res.data });
      else if (res.status === 422) dispatch({ type: "failed", error: "expired", clearProposal: true });
      else dispatch({ type: "turnFailed", error: agentErrorKind(res), fallback: unavailable(res) });
    },
    [nextId],
  );

  /** Fallback form: "Check" sends the text to `chat/preview`. */
  const check = useCallback(
    async (rawText: string) => {
      const text = rawText.trim();
      if (!text || stateRef.current.busy) return;
      dispatch({ type: "sent", id: nextId("u"), text });
      stateRef.current = { ...stateRef.current, busy: true };
      const res = await preview(text, []);
      if (res.ok) dispatch({ type: "previewed", proposal: res.data });
      else dispatch({ type: "failed", error: agentErrorKind(res) });
    },
    [nextId],
  );

  /** A clarifying question chip: the chosen option goes to `chat/preview` as the answer. */
  const answer = useCallback(async (optionId: string) => {
    const cur = stateRef.current;
    const question = cur.proposal?.question;
    if (!cur.proposal || !question || cur.busy) return;
    dispatch({ type: "busy" });
    stateRef.current = { ...cur, busy: true };
    const res = await preview(cur.proposal.text, [...cur.asked, question.question_id], optionId);
    if (res.ok) dispatch({ type: "previewed", proposal: res.data, question: question.question_id });
    else dispatch({ type: "failed", error: agentErrorKind(res) });
  }, []);

  /** "Yes, send it". */
  const confirmProposal = useCallback(async () => {
    const cur = stateRef.current;
    if (!cur.proposal || cur.busy) return;
    dispatch({ type: "busy" });
    stateRef.current = { ...cur, busy: true };
    const res = await confirm(cur.proposal.token);
    if (res.ok) dispatch({ type: "confirmed", id: nextId("a"), res: res.data, text: textsRef.current.recorded });
    else dispatch({ type: "failed", error: agentErrorKind(res), clearProposal: res.status === 422 });
  }, [nextId]);

  /** "Not now": nothing was created, so nothing is sent to the service. */
  const decline = useCallback(() => {
    if (!stateRef.current.proposal) return;
    dispatch({ type: "declined", id: nextId("a"), text: textsRef.current.declined });
  }, [nextId]);

  return { ...state, send, check, answer, confirm: confirmProposal, decline };
}
