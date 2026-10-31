import type { Sb, Tables } from "../supabase/types";
import { eqFilter, subscribeTable, unwrap } from "./realtime";

export type NotificationRow = Tables<"notifications">;

/** The recipient's notifications, newest first (RLS: the alias must be the caller's). */
export async function listNotifications(sb: Sb, alias: string, limit = 30): Promise<NotificationRow[]> {
  return unwrap(
    await sb.from("notifications").select("*").eq("alias", alias).order("created_at", { ascending: false }).limit(limit),
  );
}

/**
 * New notifications for one alias (ticket resolved, incident broadcast). This is the
 * only table a student subscribes to. Returns an unsubscribe function.
 */
export function subscribeNotifications(sb: Sb, alias: string, onChange: (n: NotificationRow) => void): () => void {
  return subscribeTable<NotificationRow>(
    sb,
    "notifications",
    (c) => {
      if (c.kind === "insert") onChange(c.row);
    },
    { filter: eqFilter("alias", alias) },
  );
}
