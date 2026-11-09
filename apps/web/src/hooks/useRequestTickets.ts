"use client";

import { useEffect, useState } from "react";
import { listTicketsForRequests, type TicketRow } from "@/lib/repos/tickets";
import { createBrowserSupabase } from "@/lib/supabase/browser";

/**
 * The first ticket of each request, by request id, for the Pulse building list. RLS decides what the
 * caller sees: staff get their office's tickets, an admin all. A failed read gives an empty map, so the
 * list still shows the requests, just without ticket links.
 */
export function useRequestTickets(requestIds: readonly string[]): Map<string, TicketRow> {
  const [tickets, setTickets] = useState<Map<string, TicketRow>>(new Map());
  const key = [...requestIds].sort().join(",");
  useEffect(() => {
    let live = true;
    const ids = key ? key.split(",") : [];
    try {
      listTicketsForRequests(createBrowserSupabase(), ids)
        .then((rows) => {
          if (!live) return;
          const byRequest = new Map<string, TicketRow>();
          for (const t of rows) if (t.request_id && !byRequest.has(t.request_id)) byRequest.set(t.request_id, t);
          setTickets(byRequest);
        })
        .catch(() => live && setTickets(new Map()));
    } catch {
      // No Supabase client: no ticket links.
    }
    return () => {
      live = false;
    };
  }, [key]);
  return tickets;
}
