import type { Sb, Tables } from "../supabase/types";
import { subscribeTable, unwrap } from "./realtime";

/** A full `predictions` row (staff and admin only: students use `predictions_student_v`). */
export type PredictionRow = Tables<"predictions">;

/** The few columns the Pulse map needs to colour a dot. */
export type PredictionBrief = Pick<PredictionRow, "id" | "request_id" | "category" | "priority" | "created_at">;

const BRIEF_COLUMNS = "id, request_id, category, priority, created_at";

/** Predictions by id (the ones behind review items). RLS drops those the caller may not see. */
export async function listPredictionsByIds(sb: Sb, ids: string[]): Promise<PredictionRow[]> {
  if (ids.length === 0) return [];
  return unwrap(await sb.from("predictions").select("*").in("id", ids));
}

/** Every prediction of one request, newest first. The first row is the current decision. */
export async function listPredictionsForRequest(sb: Sb, requestId: string): Promise<PredictionRow[]> {
  return unwrap(await sb.from("predictions").select("*").eq("request_id", requestId).order("created_at", { ascending: false }));
}

/**
 * The latest category and priority of each given request, for map dots. A request that was
 * predicted twice (for example before and after a clarification) keeps its newest row.
 */
export async function listLatestPredictions(sb: Sb, requestIds: string[]): Promise<PredictionBrief[]> {
  if (requestIds.length === 0) return [];
  const rows = unwrap(
    await sb.from("predictions").select(BRIEF_COLUMNS).in("request_id", requestIds).order("created_at", { ascending: false }),
  ) as PredictionBrief[];
  const seen = new Set<string>();
  return rows.filter((r) => (seen.has(r.request_id) ? false : (seen.add(r.request_id), true)));
}

/** Recent predictions carrying any of the given flags, newest first (staff and admin). */
export async function listFlaggedPredictions(sb: Sb, flags: readonly string[], limit = 30): Promise<PredictionRow[]> {
  return unwrap(
    await sb.from("predictions").select("*").overlaps("flags", [...flags]).order("created_at", { ascending: false }).limit(limit),
  );
}

/** Prediction inserts (a new decision, a review item, a map dot's colour). Returns an unsubscribe function. */
export function subscribePredictions(sb: Sb, onChange: (row: PredictionRow) => void): () => void {
  return subscribeTable<PredictionRow>(sb, "predictions", (c) => {
    if (c.kind === "insert") onChange(c.row);
  });
}
