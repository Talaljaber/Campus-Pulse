"use client";

import { useCallback, useEffect, useReducer, useState } from "react";
import { resolveIncident } from "@/lib/incidents";
import { listOpenIncidents, subscribeIncidents } from "@/lib/repos/incidents";
import { listOutbox, subscribeOutbox } from "@/lib/repos/outbox";
import { listLatestPredictions, subscribePredictions } from "@/lib/repos/predictions";
import { listRequestsWithLocation, subscribeRequestsWithLocation } from "@/lib/repos/requests";
import { INITIAL_PULSE, pulseReducer } from "@/lib/pulse/state";
import { staffErrorKind, type StaffErrorKind } from "@/lib/staff/service";
import { createBrowserSupabase } from "@/lib/supabase/browser";
import type { LoadState } from "./useTicketQueue";

/**
 * Everything the Pulse page shows, live: located requests and the labels their predictions
 * gave (a dot needs both), open incidents, broadcasts and the feed. One snapshot read, then
 * Realtime on `requests`, `predictions`, `incidents` and `outbox`. RLS limits staff to their
 * office's rows; an admin gets everything. Unsubscribes on unmount.
 */
export function usePulse() {
  const [state, dispatch] = useReducer(pulseReducer, INITIAL_PULSE);
  const [load, setLoad] = useState<LoadState>("loading");
  const [resolving, setResolving] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let live = true;
    const offs: Array<() => void> = [];
    try {
      const sb = createBrowserSupabase();
      (async () => {
        try {
          const [requests, incidents, broadcasts] = await Promise.all([
            listRequestsWithLocation(sb),
            listOpenIncidents(sb),
            listOutbox(sb, { kind: "broadcast", limit: 20 }),
          ]);
          const predictions = await listLatestPredictions(sb, requests.map((r) => r.id));
          if (!live) return;
          dispatch({ type: "snapshot", requests, predictions, incidents, broadcasts });
          setLoad("ready");
        } catch {
          if (live) setLoad("error");
        }
      })();
      offs.push(
        subscribeRequestsWithLocation(sb, (row) => live && dispatch({ type: "request", row })),
        subscribePredictions(
          sb,
          (p) => live && dispatch({ type: "prediction", requestId: p.request_id, category: p.category, priority: p.priority }),
        ),
        subscribeIncidents(sb, (row) => live && dispatch({ type: "incident", row, at: new Date().toISOString() })),
        subscribeOutbox(sb, (row) => live && dispatch({ type: "broadcast", row })),
      );
    } catch {
      queueMicrotask(() => live && setLoad("error"));
    }
    return () => {
      live = false;
      offs.forEach((off) => off());
    };
  }, [nonce]);

  const reload = useCallback(() => {
    setLoad("loading");
    setNonce((n) => n + 1);
  }, []);

  /** Resolves an incident through the API. Returns the notified count, or the error kind. */
  const resolve = useCallback(
    async (id: string, note?: string): Promise<{ ok: true; notified: number } | { ok: false; kind: StaffErrorKind }> => {
      setResolving(id);
      const res = await resolveIncident(id, note);
      setResolving(null);
      if (!res.ok) return { ok: false, kind: staffErrorKind(res) };
      const closed = res.data.incident;
      const row = {
        id: closed.id,
        building_id: closed.building,
        category: closed.category,
        title: closed.title,
        priority: closed.priority,
        report_count: closed.report_count,
        status: "resolved",
        opened_at: closed.opened_at,
        resolved_at: closed.resolved_at,
        created_at: closed.opened_at,
        office: null,
      };
      dispatch({ type: "incident", row, at: new Date().toISOString() });
      return { ok: true, notified: res.data.notified_reporters };
    },
    [],
  );

  return { state, load, resolving, reload, resolve };
}
