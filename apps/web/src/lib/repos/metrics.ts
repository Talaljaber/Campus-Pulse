import type { Sb, Tables } from "../supabase/types";
import { unwrap } from "./realtime";

export type RedteamRunRow = Tables<"redteam_runs">;
export type EventRow = Tables<"events">;

/**
 * Red-team scorecard history, newest first (staff and admin). The live model numbers
 * come from `GET /v1/metrics` through the AI proxy, not from the database.
 */
export async function listRedteamRuns(sb: Sb, limit = 20): Promise<RedteamRunRow[]> {
  return unwrap(await sb.from("redteam_runs").select("*").order("created_at", { ascending: false }).limit(limit));
}

/** The newest audit events (injection attempts, gaming flags), staff and admin. */
export async function listRecentEvents(sb: Sb, limit = 50): Promise<EventRow[]> {
  return unwrap(await sb.from("events").select("*").order("at", { ascending: false }).limit(limit));
}
