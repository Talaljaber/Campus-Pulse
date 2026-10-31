/**
 * Builds the human-review queue the staff page shows from three reads: the open
 * `review_queue` rows, the predictions behind them and the requests those belong to.
 * RLS may hide a prediction or request from staff (a distress item has no ticket, so no
 * office owns it); such an item is still listed, with what is known.
 */
import type { Evidence, Explanation, Tier } from "@/lib/ai/types";
import type { PredictionRow } from "@/lib/repos/predictions";
import type { RequestRow, ReviewRow } from "@/lib/repos/requests";
import { evidenceFromPrediction, explanationFromPrediction, tierOf } from "./explanation";

export interface ReviewView {
  /** The `review_queue` row id (React key). */
  id: string;
  /** What `POST /v1/feedback` takes. */
  predictionId: string;
  requestId: string | null;
  createdAt: string;
  /** The request text, when the caller may read it. */
  text: string | null;
  category: string | null;
  priority: string | null;
  /** The conformal sets: more than one label means the model could not decide. */
  setCat: string[];
  setPri: string[];
  flags: string[];
  /** A distress signal: nothing to classify, a person has to look. */
  distress: boolean;
  tier: Tier | undefined;
  explanation: Explanation | null;
  evidence: Evidence[];
}

export function buildReviewViews(
  reviews: readonly ReviewRow[],
  predictions: readonly PredictionRow[],
  requests: readonly RequestRow[],
): ReviewView[] {
  const pById = new Map(predictions.map((p) => [p.id, p]));
  const rById = new Map(requests.map((r) => [r.id, r]));
  return reviews.map((rv) => {
    const p = pById.get(rv.prediction_id);
    const req = p ? rById.get(p.request_id) : undefined;
    return {
      id: rv.id,
      predictionId: rv.prediction_id,
      requestId: p?.request_id ?? null,
      createdAt: rv.created_at,
      text: req?.raw_text ?? null,
      category: p?.category ?? null,
      priority: p?.priority ?? null,
      setCat: p?.set_cat ?? [],
      setPri: p?.set_pri ?? [],
      flags: p?.flags ?? [],
      distress: (p?.flags ?? []).includes("distress"),
      tier: p ? tierOf(p) : undefined,
      explanation: p ? explanationFromPrediction(p) : null,
      evidence: p ? evidenceFromPrediction(p) : [],
    };
  });
}

/** Removes one review item (after a confirmation or correction). */
export function withoutReview(items: readonly ReviewView[], predictionId: string): ReviewView[] {
  return items.filter((i) => i.predictionId !== predictionId);
}

/**
 * Whether a new prediction may add a review item, so the page knows to re-read the queue.
 * `review_queue` is not in the Realtime publication, so the prediction insert is the signal.
 */
export function mayNeedReview(flags: readonly string[]): boolean {
  return flags.includes("needs_review") || flags.includes("distress");
}
