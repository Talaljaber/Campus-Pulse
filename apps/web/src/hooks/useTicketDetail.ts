"use client";

import { useCallback, useEffect, useState } from "react";
import type { CounterfactualView } from "@/lib/ai/types";
import { fetchCounterfactual } from "@/lib/chat/service";
import { listPredictionsForRequest } from "@/lib/repos/predictions";
import { listRequestsByIds } from "@/lib/repos/requests";
import { buildDetail, type DetailView } from "@/lib/staff/detail";
import { createBrowserSupabase } from "@/lib/supabase/browser";
import type { LoadState } from "./useTicketQueue";

interface Loaded {
  requestId: string;
  state: LoadState;
  detail: DetailView | null;
}

/**
 * The request behind the selected ticket, with its current decision and explanation, read
 * on demand (the queue itself stays light). `counterfactual` is the live "what if this word
 * were removed" answer for the same request, fetched through the AI proxy.
 */
export function useTicketDetail(requestId: string | null) {
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [cf, setCf] = useState<{ requestId: string; view: CounterfactualView } | null>(null);

  useEffect(() => {
    if (!requestId) return;
    let live = true;
    try {
      const sb = createBrowserSupabase();
      Promise.all([listRequestsByIds(sb, [requestId]), listPredictionsForRequest(sb, requestId)])
        .then(([requests, predictions]) => {
          if (!live) return;
          const request = requests[0];
          setLoaded({ requestId, state: request ? "ready" : "error", detail: request ? buildDetail(request, predictions) : null });
        })
        .catch(() => live && setLoaded({ requestId, state: "error", detail: null }));
    } catch {
      queueMicrotask(() => live && setLoaded({ requestId, state: "error", detail: null }));
    }
    return () => {
      live = false;
    };
  }, [requestId]);

  const askCounterfactual = useCallback(
    async (token: string) => {
      if (!requestId) return;
      const res = await fetchCounterfactual(requestId, token);
      if (res.ok) setCf({ requestId, view: res.data });
    },
    [requestId],
  );

  // Derived, so switching tickets never shows the previous ticket's data while the next one loads.
  const current = loaded && loaded.requestId === requestId ? loaded : null;
  return {
    load: (requestId ? (current?.state ?? "loading") : "ready") as LoadState,
    detail: current?.detail ?? null,
    counterfactual: cf && cf.requestId === requestId ? cf.view : null,
    askCounterfactual,
  };
}
