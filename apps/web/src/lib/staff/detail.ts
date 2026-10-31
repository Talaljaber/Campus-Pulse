/** The request-detail view of a ticket: the request, its current decision and the explanation. */
import type { Evidence, Explanation, Tier } from "@/lib/ai/types";
import type { PredictionRow } from "@/lib/repos/predictions";
import type { RequestRow } from "@/lib/repos/requests";
import { evidenceFromPrediction, explanationFromPrediction, tierOf } from "./explanation";

export interface DetailView {
  requestId: string;
  text: string;
  lang: string | null;
  /** `voice` when the student dictated the request. */
  inputMode: string | null;
  simulated: boolean;
  buildingId: string | null;
  room: string | null;
  createdAt: string;
  /** The current decision: the newest prediction of the request. Null when the caller cannot read one. */
  prediction: {
    id: string;
    category: string | null;
    priority: string | null;
    flags: string[];
    tier: Tier | undefined;
    explanation: Explanation | null;
    evidence: Evidence[];
  } | null;
}

/** `predictions` newest first (as `listPredictionsForRequest` returns them); the first is current. */
export function buildDetail(request: RequestRow, predictions: readonly PredictionRow[]): DetailView {
  const p = predictions[0];
  return {
    requestId: request.id,
    text: request.raw_text,
    lang: request.lang,
    inputMode: request.input_mode,
    simulated: request.simulated,
    buildingId: request.building_id,
    room: request.room,
    createdAt: request.created_at,
    prediction: p
      ? {
          id: p.id,
          category: p.category,
          priority: p.priority,
          flags: p.flags,
          tier: tierOf(p),
          explanation: explanationFromPrediction(p),
          evidence: evidenceFromPrediction(p),
        }
      : null,
  };
}
