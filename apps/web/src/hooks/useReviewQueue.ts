"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { listPredictionsByIds, subscribePredictions } from "@/lib/repos/predictions";
import { listRequestsByIds, listReviewQueue } from "@/lib/repos/requests";
import { buildReviewViews, mayNeedReview, withoutReview, type ReviewView } from "@/lib/staff/review";
import { sendFeedback, staffErrorKind, type Correction, type StaffErrorKind } from "@/lib/staff/service";
import { createBrowserSupabase } from "@/lib/supabase/browser";
import type { Sb } from "@/lib/supabase/types";
import type { LoadState } from "./useTicketQueue";

/** Waits this long after a flagged prediction arrives, so a burst becomes one re-read. */
const REFRESH_DELAY_MS = 400;

async function readQueue(sb: Sb): Promise<ReviewView[]> {
  const reviews = await listReviewQueue(sb);
  const predictions = await listPredictionsByIds(sb, reviews.map((r) => r.prediction_id));
  const requests = await listRequestsByIds(sb, [...new Set(predictions.map((p) => p.request_id))]);
  return buildReviewViews(reviews, predictions, requests);
}

/** What a confirm or correct returns: the memory message is ours (`staff.memoryToast`), so only success or the error kind matters. */
export type ReviewOutcome = { ok: true; ticketId: string | null } | { ok: false; kind: StaffErrorKind };

/**
 * The human-review queue. It reads the open `review_queue` rows with their predictions and
 * requests, and re-reads when a new prediction that may need review arrives (the queue table
 * itself is not in the Realtime publication). Confirming or correcting sends
 * `POST /v1/feedback` and drops the item once the service accepts it.
 */
export function useReviewQueue() {
  const [items, setItems] = useState<ReviewView[]>([]);
  const [load, setLoad] = useState<LoadState>("loading");
  const [pending, setPending] = useState<ReadonlySet<string>>(new Set());
  const [nonce, setNonce] = useState(0);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    let live = true;
    let off: (() => void) | undefined;
    try {
      const sb = createBrowserSupabase();
      const refresh = () =>
        readQueue(sb)
          .then((next) => {
            if (live) {
              setItems(next);
              setLoad("ready");
            }
          })
          .catch(() => {
            // A failed background refresh keeps what is on screen; only the first read shows the error.
            if (live) setLoad((cur) => (cur === "loading" ? "error" : cur));
          });
      void refresh();
      off = subscribePredictions(sb, (row) => {
        if (!mayNeedReview(row.flags)) return;
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

  const decide = useCallback(async (predictionId: string, correction: Correction): Promise<ReviewOutcome> => {
    setPending((p) => new Set(p).add(predictionId));
    const res = await sendFeedback(predictionId, correction);
    setPending((p) => {
      const next = new Set(p);
      next.delete(predictionId);
      return next;
    });
    if (!res.ok) return { ok: false, kind: staffErrorKind(res) };
    setItems((cur) => withoutReview(cur, predictionId));
    return { ok: true, ticketId: res.data.ticket?.id ?? null };
  }, []);

  const confirm = useCallback((predictionId: string) => decide(predictionId, { category: null, priority: null, note: "" }), [decide]);

  return { items, load, pending, reload, confirm, correct: decide };
}
