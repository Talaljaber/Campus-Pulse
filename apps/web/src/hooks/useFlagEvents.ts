"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { listFlaggedPredictions, subscribePredictions } from "@/lib/repos/predictions";
import { listRequestsByIds } from "@/lib/repos/requests";
import { WATCHED_FLAGS, buildFlagEvents, type FlagEvent } from "@/lib/staff/flags";
import { createBrowserSupabase } from "@/lib/supabase/browser";
import type { LoadState } from "./useTicketQueue";

const REFRESH_DELAY_MS = 400;

/**
 * Recent requests whose prediction carried an injection, unsupported-urgency or gaming
 * flag. It reads once and re-reads (debounced) when a new prediction with such a flag
 * arrives. Which flags a viewer may see is decided in the panel by audience, not here.
 */
export function useFlagEvents() {
  const [events, setEvents] = useState<FlagEvent[]>([]);
  const [load, setLoad] = useState<LoadState>("loading");
  const [nonce, setNonce] = useState(0);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    let live = true;
    let off: (() => void) | undefined;
    try {
      const sb = createBrowserSupabase();
      const refresh = async () => {
        try {
          const predictions = await listFlaggedPredictions(sb, WATCHED_FLAGS);
          const requests = await listRequestsByIds(sb, [...new Set(predictions.map((p) => p.request_id))]);
          if (!live) return;
          setEvents(buildFlagEvents(predictions, requests));
          setLoad("ready");
        } catch {
          if (live) setLoad((cur) => (cur === "loading" ? "error" : cur));
        }
      };
      void refresh();
      off = subscribePredictions(sb, (row) => {
        if (!row.flags.some((f) => (WATCHED_FLAGS as readonly string[]).includes(f))) return;
        clearTimeout(timer.current);
        timer.current = setTimeout(() => void refresh(), REFRESH_DELAY_MS);
      });
    } catch {
      queueMicrotask(() => live && setLoad("error"));
    }
    return () => {
      live = false;
      clearTimeout(timer.current);
      off?.();
    };
  }, [nonce]);

  const reload = useCallback(() => {
    setLoad("loading");
    setNonce((n) => n + 1);
  }, []);

  return { events, load, reload };
}
