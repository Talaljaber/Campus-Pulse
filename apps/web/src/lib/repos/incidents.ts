import type { Sb, Tables } from "../supabase/types";
import { subscribeTable, unwrap } from "./realtime";

export type IncidentRow = Tables<"incidents">;

/** Open incidents, newest first. Staff see their office's, admin sees all (RLS). */
export async function listOpenIncidents(sb: Sb): Promise<IncidentRow[]> {
  return unwrap(await sb.from("incidents").select("*").eq("status", "open").order("opened_at", { ascending: false }));
}

/** Incident inserts and updates (new ring, report bump, resolve). Returns an unsubscribe function. */
export function subscribeIncidents(sb: Sb, onChange: (i: IncidentRow) => void): () => void {
  return subscribeTable<IncidentRow>(sb, "incidents", (c) => onChange(c.row));
}
