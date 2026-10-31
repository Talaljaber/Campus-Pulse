"use client";

import { useCallback, useEffect, useState } from "react";
import { OUTBOX_LIMIT, mergeOutbox, sortOutbox } from "@/lib/outbox/view";
import { listOutbox, subscribeOutbox, type OutboxRow } from "@/lib/repos/outbox";
import { createBrowserSupabase } from "@/lib/supabase/browser";
import type { LoadState } from "./useTicketQueue";

/**
 * The newest outbox rows (staff and admin see every row, by row-level security), kept current with
 * Realtime inserts and updates, so a message that is rejected or sent shows up as it happens.
 */
export function useOutbox() {
  const [rows, setRows] = useState<OutboxRow[]>([]);
  const [load, setLoad] = useState<LoadState>("loading");
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let live = true;
    let off: (() => void) | undefined;
    try {
      const sb = createBrowserSupabase();
      listOutbox(sb, { limit: OUTBOX_LIMIT })
        .then((list) => {
          if (!live) return;
          // Rows that arrived live while the snapshot was loading are kept; the newest copy of an id wins.
          setRows((cur) => cur.reduce((acc, r) => mergeOutbox(acc, r), sortOutbox(list)));
          setLoad("ready");
        })
        .catch(() => {
          if (live) setLoad("error");
        });
      off = subscribeOutbox(sb, (row) => setRows((cur) => mergeOutbox(cur, row)));
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

  return { rows, load, reload };
}
