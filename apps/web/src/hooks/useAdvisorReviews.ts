"use client";

import { useCallback, useEffect, useState } from "react";
import type { ReviewItem, ReviewStatus } from "@/lib/ai/types";
import { fetchReviews, forwardErrorKind, forwardReview, sendFeedback, staffErrorKind, type StaffErrorKind } from "@/lib/staff/service";
import type { LoadState } from "./useTicketQueue";

export type AdvisorOutcome = { ok: true } | { ok: false; kind: StaffErrorKind };

/**
 * The advisor's review queue (`GET /v1/reviews?status=`): the caller's students' items first, then
 * their office's unassigned ones. Confirm reuses `POST /v1/feedback`; forward is
 * `POST /v1/reviews/{id}/forward`. A resolved item leaves the list at once. Changing `status`
 * shows the loading state until that list arrives (never the previous tab's items).
 */
export function useAdvisorReviews(status: ReviewStatus) {
  const [data, setData] = useState<{ status: ReviewStatus; items: ReviewItem[] } | null>(null);
  const [failed, setFailed] = useState<ReviewStatus | null>(null);
  const [pending, setPending] = useState<ReadonlySet<string>>(new Set());
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let live = true;
    void fetchReviews(status).then((res) => {
      if (!live) return;
      if (res.ok) {
        setData({ status, items: res.data });
        setFailed(null);
      } else {
        setFailed(status);
      }
    });
    return () => {
      live = false;
    };
  }, [status, nonce]);

  const items = data?.status === status ? data.items : [];
  // A failed background refresh keeps what is on screen; only a first read shows the error.
  const load: LoadState = data?.status === status ? "ready" : failed === status ? "error" : "loading";

  /** Reads again; a failure shows the error state only when nothing is on screen. */
  const reload = useCallback(() => {
    setFailed(null);
    setNonce((n) => n + 1);
  }, []);

  const run = useCallback(async (id: string, call: () => Promise<AdvisorOutcome>): Promise<AdvisorOutcome> => {
    setPending((p) => new Set(p).add(id));
    const out = await call();
    setPending((p) => {
      const next = new Set(p);
      next.delete(id);
      return next;
    });
    if (out.ok) setData((cur) => (cur ? { ...cur, items: cur.items.filter((i) => i.id !== id) } : cur));
    return out;
  }, []);

  const confirm = useCallback(
    (item: ReviewItem) =>
      run(item.id, async () => {
        const res = await sendFeedback(item.prediction_id, { category: null, priority: null, note: "" });
        return res.ok ? { ok: true } : { ok: false, kind: staffErrorKind(res) };
      }),
    [run],
  );

  const forward = useCallback(
    (item: ReviewItem, office: string, note: string) =>
      run(item.id, async () => {
        const res = await forwardReview(item.id, office, note);
        return res.ok ? { ok: true } : { ok: false, kind: forwardErrorKind(res) };
      }),
    [run],
  );

  return { items, load, pending, reload, confirm, forward };
}
