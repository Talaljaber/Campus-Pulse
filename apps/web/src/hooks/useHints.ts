"use client";

import { useCallback, useEffect, useState } from "react";
import { listHints } from "@/lib/repos/hints";
import type { HintRow } from "@/lib/tickets/types";
import { createBrowserSupabase } from "@/lib/supabase/browser";
import type { LoadState } from "./useTicketQueue";

/** Past staff corrections (`ticket_hints`, staff and admin only by RLS), newest first. Read once; reload on demand. */
export function useHints() {
  const [hints, setHints] = useState<HintRow[]>([]);
  const [load, setLoad] = useState<LoadState>("loading");
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let live = true;
    try {
      listHints(createBrowserSupabase())
        .then((rows) => {
          if (!live) return;
          setHints(rows);
          setLoad("ready");
        })
        .catch(() => live && setLoad("error"));
    } catch {
      queueMicrotask(() => live && setLoad("error"));
    }
    return () => {
      live = false;
    };
  }, [nonce]);

  const reload = useCallback(() => {
    setLoad("loading");
    setNonce((n) => n + 1);
  }, []);

  return { hints, load, reload };
}
