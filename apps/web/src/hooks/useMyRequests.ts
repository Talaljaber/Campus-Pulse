"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { listLastActivity, listMyTickets, subscribeTickets, type TicketRow } from "@/lib/repos/tickets";
import { createBrowserSupabase } from "@/lib/supabase/browser";
import type { LoadState } from "./useTicketQueue";

/** The tickets the viewer requested (students and staff alike): `requester_alias === myAlias`, kept live. */
export function useMyRequests(myAlias: string | null) {
  const [rows, setRows] = useState<TicketRow[]>([]);
  const [last, setLast] = useState<ReadonlyMap<string, string>>(new Map());
  const [load, setLoad] = useState<LoadState>("loading");
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let live = true;
    let off: (() => void) | undefined;
    if (!myAlias) {
      queueMicrotask(() => live && setLoad("ready"));
      return () => {
        live = false;
      };
    }
    try {
      const sb = createBrowserSupabase();
      (async () => {
        try {
          const mine = await listMyTickets(sb, myAlias);
          const times = await listLastActivity(sb, mine.map((r) => r.id)).catch(() => new Map<string, string>());
          if (!live) return;
          setRows(mine.filter((r) => r.requester_alias === myAlias));
          setLast(times);
          setLoad("ready");
        } catch {
          if (live) setLoad("error");
        }
      })();
      off = subscribeTickets(sb, null, (row) => {
        if (!live || row.requester_alias !== myAlias) return;
        setRows((cur) => (cur.some((r) => r.id === row.id) ? cur.map((r) => (r.id === row.id ? row : r)) : [row, ...cur]));
        setLast((cur) => new Map(cur).set(row.id, new Date().toISOString()));
      });
    } catch {
      queueMicrotask(() => live && setLoad("error"));
    }
    return () => {
      live = false;
      off?.();
    };
  }, [myAlias, nonce]);

  const reload = useCallback(() => {
    setLoad("loading");
    setNonce((n) => n + 1);
  }, []);

  /** Tickets with the time of their last visible change (a thread row, else the ticket's own newest timestamp). */
  const tickets = useMemo(
    () =>
      rows.map((r) => ({
        ...r,
        lastUpdate: last.get(r.id) ?? [r.created_at, r.clock_started_at, r.resolved_at].filter((x): x is string => !!x).sort().at(-1)!,
      })),
    [rows, last],
  );

  return { tickets, load, reload };
}

export type MyTicket = ReturnType<typeof useMyRequests>["tickets"][number];
