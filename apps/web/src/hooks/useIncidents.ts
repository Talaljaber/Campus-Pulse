"use client";

import { useCallback, useEffect, useState } from "react";
import { applyIncident, resolveIncident } from "@/lib/incidents";
import { listOpenIncidents, subscribeIncidents, type IncidentRow } from "@/lib/repos/incidents";
import { staffErrorKind, type StaffErrorKind } from "@/lib/staff/service";
import { createBrowserSupabase } from "@/lib/supabase/browser";
import type { LoadState } from "./useTicketQueue";

/**
 * Open incidents (staff of the office, or every office for an admin, by RLS), kept live:
 * a new incident appears, a report count rises, a resolved one leaves. Shared by `/staff`
 * and `/pulse`. `resolve` calls the API and removes the incident once it accepts.
 */
export function useIncidents() {
  const [rows, setRows] = useState<IncidentRow[]>([]);
  const [load, setLoad] = useState<LoadState>("loading");
  const [resolving, setResolving] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let live = true;
    let off: (() => void) | undefined;
    try {
      const sb = createBrowserSupabase();
      listOpenIncidents(sb)
        .then((list) => {
          if (!live) return;
          setRows(list);
          setLoad("ready");
        })
        .catch(() => live && setLoad("error"));
      off = subscribeIncidents(sb, (row) => live && setRows((cur) => applyIncident(cur, row)));
    } catch {
      queueMicrotask(() => live && setLoad("error"));
    }
    return () => {
      live = false;
      off?.();
    };
  }, [nonce]);

  const reload = useCallback(() => {
    setLoad("loading");
    setNonce((n) => n + 1);
  }, []);

  /** Resolves the incident. Returns the number of notified reporters, or the error kind. */
  const resolve = useCallback(async (id: string, note?: string): Promise<{ ok: true; notified: number } | { ok: false; kind: StaffErrorKind }> => {
    setResolving(id);
    const res = await resolveIncident(id, note);
    setResolving(null);
    if (!res.ok) return { ok: false, kind: staffErrorKind(res) };
    setRows((cur) => cur.filter((i) => i.id !== id));
    return { ok: true, notified: res.data.notified_reporters };
  }, []);

  return { rows, load, resolving, reload, resolve };
}
