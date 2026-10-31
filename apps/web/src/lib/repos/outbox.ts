import type { Sb, Tables } from "../supabase/types";
import { subscribeTable, unwrap } from "./realtime";

export type OutboxRow = Tables<"outbox">;

/**
 * The outbox, newest first. A student sees only the rows sent for their alias; staff
 * and admin see all (RLS). `kind` narrows to one purpose (`booking`, `alert`, ...).
 */
export async function listOutbox(sb: Sb, opts: { kind?: string; limit?: number } = {}): Promise<OutboxRow[]> {
  let q = sb.from("outbox").select("*").order("created_at", { ascending: false }).limit(opts.limit ?? 50);
  if (opts.kind) q = q.eq("kind", opts.kind);
  return unwrap(await q);
}

/** Outbox inserts and updates (a broadcast going out, a status change). Returns an unsubscribe function. */
export function subscribeOutbox(sb: Sb, onChange: (row: OutboxRow) => void): () => void {
  return subscribeTable<OutboxRow>(sb, "outbox", (c) => onChange(c.row));
}
