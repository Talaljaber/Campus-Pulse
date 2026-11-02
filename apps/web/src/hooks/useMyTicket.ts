"use client";

import { useCallback, useEffect, useState } from "react";
import type { AiFail, AiResult } from "@/lib/ai/result";
import type { TicketOut } from "@/lib/ai/types";
import { getTicket, listActivity, subscribeActivity, subscribeTicket, type TicketRow } from "@/lib/repos/tickets";
import { applyTicketOut } from "@/lib/staff/tickets";
import { createBrowserSupabase } from "@/lib/supabase/browser";
import { postComment, postStudentAction } from "@/lib/tickets/service";
import type { ActivityRow, CommentResponse, StudentActionRequest } from "@/lib/tickets/types";
import { mergeActivity, type ThreadLoad } from "./useTicketThread";

/**
 * One of the viewer's own tickets with its thread, read under RLS and kept live. A ticket that is not
 * the caller's own (`requester_alias !== myAlias`) counts as not found, whatever RLS lets through.
 * The two actions call the AI service and return its result; the caller shows the toast.
 */
export function useMyTicket(ticketId: string, myAlias: string | null) {
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
          if (!row || !myAlias || row.requester_alias !== myAlias) {
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
      offTicket = subscribeTicket(sb, ticketId, (row) => live && row.requester_alias === myAlias && setTicket(row));
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

  const refreshActivity = useCallback(async () => {
    try {
      setActivity(await listActivity(createBrowserSupabase(), ticketId));
    } catch {
      // The live channel will bring the rows.
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

  /** A message from the requester (never internal, never a status). On a finished ticket the server reopens it. */
  const comment = useCallback(
    (body: string) =>
      run<CommentResponse>(
        () => postComment(ticketId, { body, internal: false, status: null }),
        (data) => {
          setTicket((cur) => (cur ? applyTicketOut(cur, data.ticket) : cur));
          setActivity((cur) => mergeActivity(cur, data.activity));
        },
      ),
    [run, ticketId],
  );

  const act = useCallback(
    (req: StudentActionRequest) =>
      run<TicketOut>(
        () => postStudentAction(ticketId, req),
        (out) => {
          setTicket((cur) => (cur ? applyTicketOut(cur, out) : cur));
          void refreshActivity();
        },
      ),
    [run, ticketId, refreshActivity],
  );

  return { ticket, activity, load, busy, reload, comment, act };
}
