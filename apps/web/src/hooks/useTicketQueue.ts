"use client";

import { useCallback, useEffect, useState } from "react";
import type { TicketStatus } from "@/lib/ai/types";
import { listTicketLinks, listTickets, subscribeTickets } from "@/lib/repos/tickets";
import { setTicketStatus, staffErrorKind, type StaffErrorKind } from "@/lib/staff/service";
import { applyTicketOut, mergeLive, withLinks, type TicketView } from "@/lib/staff/tickets";
import { createBrowserSupabase } from "@/lib/supabase/browser";

export type LoadState = "loading" | "ready" | "error";

/**
 * The ticket queue of one office (`null` = every ticket the caller may see, for an admin).
 * It reads once, then follows Realtime inserts and updates. RLS is what limits staff to
 * their office; the `office` argument only narrows an admin's view. A ticket that arrives
 * live has no Linear link yet (the link is written a moment later), so its link is read once.
 */
export function useTicketQueue(office: string | null) {
  const [tickets, setTickets] = useState<TicketView[]>([]);
  const [load, setLoad] = useState<LoadState>("loading");
  const [pending, setPending] = useState<ReadonlySet<string>>(new Set());
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let live = true;
    let off: (() => void) | undefined;
    try {
      const sb = createBrowserSupabase();
      (async () => {
        try {
          const rows = await listTickets(sb, office);
          const links = await listTicketLinks(sb, rows.map((r) => r.id));
          if (!live) return;
          setTickets(withLinks(rows, links));
          setLoad("ready");
        } catch {
          if (live) setLoad("error");
        }
      })();
      off = subscribeTickets(sb, office, (row) => {
        if (!live) return;
        setTickets((cur) => mergeLive(cur, row));
        listTicketLinks(sb, [row.id])
          .then((links) => {
            const link = links[0];
            if (!live || !link) return;
            setTickets((cur) =>
              cur.map((t) => (t.id === row.id ? { ...t, link: { id: link.external_id, url: link.external_url } } : t)),
            );
          })
          .catch(() => {});
      });
    } catch {
      // No Supabase client (missing env): the page shows its error state.
      queueMicrotask(() => live && setLoad("error"));
    }
    return () => {
      live = false;
      off?.();
    };
  }, [office, nonce]);

  const reload = useCallback(() => {
    setLoad("loading");
    setNonce((n) => n + 1);
  }, []);

  /** Changes a ticket's status through the API. Resolves to an error kind, or `null` on success. */
  const changeStatus = useCallback(async (id: string, status: TicketStatus): Promise<StaffErrorKind | null> => {
    setPending((p) => new Set(p).add(id));
    const res = await setTicketStatus(id, status);
    setPending((p) => {
      const next = new Set(p);
      next.delete(id);
      return next;
    });
    if (!res.ok) return staffErrorKind(res);
    setTickets((cur) => cur.map((t) => (t.id === id ? applyTicketOut(t, res.data) : t)));
    return null;
  }, []);

  return { tickets, load, pending, reload, changeStatus };
}
