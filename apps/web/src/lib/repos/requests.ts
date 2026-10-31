import type { Sb, Tables } from "../supabase/types";
import { subscribeTable, unwrap, type Change } from "./realtime";

export type RequestRow = Tables<"requests">;
/** Columns the student view exposes (no `per_model`, no cost, staff-only flags removed). */
export type StudentPredictionRow = Tables<"predictions_student_v">;
export type ReviewRow = Tables<"review_queue">;
export type BuildingRow = Tables<"buildings">;

/** A request with a building, enough to draw a dot on the Pulse map. */
export type LocatedRequest = Pick<
  RequestRow,
  "id" | "alias" | "building_id" | "room" | "status" | "simulated" | "created_at"
>;

const LOCATED_COLUMNS = "id, alias, building_id, room, status, simulated, created_at";

/**
 * The signed-in student's own requests, newest first. RLS limits the rows to the
 * caller's alias, so `limit` is the only paging control needed.
 */
export async function listMyRequests(sb: Sb, limit = 20): Promise<RequestRow[]> {
  return unwrap(await sb.from("requests").select("*").order("created_at", { ascending: false }).limit(limit));
}

/**
 * Predictions of one request through `predictions_student_v`. Students have no policy
 * on the `predictions` table itself: the view hides the staff-only flags and the
 * per-model and cost columns.
 */
export async function listMyPredictions(sb: Sb, requestId: string): Promise<StudentPredictionRow[]> {
  return unwrap(
    await sb.from("predictions_student_v").select("*").eq("request_id", requestId).order("created_at", { ascending: false }),
  );
}

/** Located requests (those with a building) for the Pulse map; staff and admin only by RLS. */
export async function listRequestsWithLocation(sb: Sb, limit = 200): Promise<LocatedRequest[]> {
  return unwrap(
    await sb
      .from("requests")
      .select(LOCATED_COLUMNS)
      .not("building_id", "is", null)
      .order("created_at", { ascending: false })
      .limit(limit),
  ) as LocatedRequest[];
}

/**
 * New requests as they arrive, for the Pulse dots. Rows without a building are dropped
 * here so the map never has to check. Returns an unsubscribe function.
 */
export function subscribeRequestsWithLocation(sb: Sb, onChange: (row: LocatedRequest) => void): () => void {
  return subscribeTable<RequestRow>(sb, "requests", (c: Change<RequestRow>) => {
    if (c.row.building_id) onChange(c.row);
  });
}

/** Open items of the human-review queue, oldest first; staff and admin only by RLS. */
export async function listReviewQueue(sb: Sb): Promise<ReviewRow[]> {
  return unwrap(await sb.from("review_queue").select("*").eq("status", "open").order("created_at", { ascending: true }));
}

/** The fictional campus buildings (any signed-in user), in code order. */
export async function listBuildings(sb: Sb): Promise<BuildingRow[]> {
  return unwrap(await sb.from("buildings").select("*").order("code", { ascending: true }));
}

/** Requests by id (staff and admin; RLS drops the ones the caller may not see). */
export async function listRequestsByIds(sb: Sb, ids: string[]): Promise<RequestRow[]> {
  if (ids.length === 0) return [];
  return unwrap(await sb.from("requests").select("*").in("id", ids));
}
