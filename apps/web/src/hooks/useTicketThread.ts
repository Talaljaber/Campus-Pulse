"use client";

import { useCallback, useEffect, useState } from "react";
import type { AiFail, AiResult } from "@/lib/ai/result";
import type { TicketOut } from "@/lib/ai/types";
import { getTicket, listActivity, subscribeActivity, subscribeTicket, type TicketRow } from "@/lib/repos/tickets";
import { forwardTicket } from "@/lib/staff/service";
import { applyForward, applyTicketOut } from "@/lib/staff/tickets";
import { createBrowserSupabase } from "@/lib/supabase/browser";
import { postComment, postPriority, postStatus } from "@/lib/tickets/service";
import type { ActivityRow, CommentRequest, CommentResponse } from "@/lib/tickets/types";

export type ThreadLoad = "loading" | "ready" | "error" | "notfound";

/** Adds or replaces a thread row by id and keeps the thread oldest first. */
export function mergeActivity(list: readonly ActivityRow[], row: ActivityRow): ActivityRow[] {
  const next = list.some((r) => r.id === row.id) ? list.map((r) => (r.id === row.id ? row : r)) : [...list, row];
  return next.sort((a, b) => a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id));
}

/**
 * One ticket and its thread, read under RLS and kept live (Realtime on the ticket and its thread).
 * A ticket the caller requested themselves counts as not found: staff never work their own ticket.
 * The actions call the AI service and return its result; the caller shows the toast.
 */
export function useTicketThread(ticketId: string, myAlias: string | null) {
  const [ticket, setTicket] = useState<TicketRow | null>(null);
  const [activity, setActivity] = useState<ActivityRow[]>([]);
  const [load, setLoad] = useState<ThreadLoad>("loading");
  const [busy, setBusy] = useState(false);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let live = true;
    let offTicket: (() => void) | undefined;
    let offActivity: (() => void) | undefined;
    try {
      const sb = createBrowserSupabase();
      (async () => {
        try {
          const [row, rows] = await Promise.all([getTicket(sb, ticketId), listActivity(sb, ticketId)]);
          if (!live) return;
          if (!row || (myAlias && row.requester_alias === myAlias)) {
            setLoad("notfound");
            return;
          }
          setTicket(row);
          setActivity(rows);
          setLoad("ready");
        } catch {
          if (live) setLoad("error");
        }
      })();
      offTicket = subscribeTicket(sb, ticketId, (row) => live && setTicket(row));
      offActivity = subscribeActivity(sb, ticketId, (row) => live && setActivity((cur) => mergeActivity(cur, row)));
    } catch {
      queueMicrotask(() => live && setLoad("error"));
    }
    return () => {
      live = false;
      offTicket?.();
      offActivity?.();
    };
  }, [ticketId, myAlias, nonce]);

  const reload = useCallback(() => {
    setLoad("loading");
    setNonce((n) => n + 1);
  }, []);

  /** Reads the thread again after an action that writes a row the response does not carry. */
  const refreshActivity = useCallback(async () => {
    try {
      setActivity(await listActivity(createBrowserSupabase(), ticketId));
    } catch {
      // The live channel will bring the rows; a failed re-read is not worth a toast.
    }
  }, [ticketId]);

  const run = useCallback(async <T,>(call: () => Promise<AiResult<T>>, onOk: (data: T) => void): Promise<{ ok: true } | AiFail> => {
    setBusy(true);
    const res = await call();
    setBusy(false);
    if (!res.ok) return res;
    onOk(res.data);
    return { ok: true };
  }, []);

  const comment = useCallback(
    (req: CommentRequest) =>
      run<CommentResponse>(
        () => postComment(ticketId, req),
        (data) => {
          setTicket((cur) => (cur ? applyTicketOut(cur, data.ticket) : cur));
          setActivity((cur) => mergeActivity(cur, data.activity));
        },
      ),
    [run, ticketId],
  );

  const changeStatus = useCallback(
    (status: "new" | "in_progress" | "solved" | "closed", note?: string) =>
      run<TicketOut>(
        () => postStatus(ticketId, status, note),
        (out) => {
          setTicket((cur) => (cur ? applyTicketOut(cur, out) : cur));
          void refreshActivity();
        },
      ),
    [run, ticketId, refreshActivity],
  );

  const forward = useCallback(
    (office: string, note: string) =>
      run<TicketOut>(
        () => forwardTicket(ticketId, office, note),
        (out) => {
          setTicket((cur) => (cur ? applyForward(cur, out, office) : cur));
          void refreshActivity();
        },
      ),
    [run, ticketId, refreshActivity],
  );

  const changePriority = useCallback(
    (priority: "low" | "medium" | "high", note?: string) =>
      run<TicketOut>(
        () => postPriority(ticketId, { priority, note }),
        (out) => {
          setTicket((cur) => (cur ? applyTicketOut(cur, out) : cur));
          void refreshActivity();
        },
      ),
    [run, ticketId, refreshActivity],
  );

  return { ticket, activity, load, busy, reload, comment, changeStatus, forward, changePriority };
}
