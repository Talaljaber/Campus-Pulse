import type { Sb } from "../supabase/types";
import type { HintRow } from "../tickets/types";
import { unwrap } from "./realtime";

export type { HintRow };

/** Only the columns the staff policy grants; selecting `embedding` would be refused. */
const HINT_COLUMNS =
  "id, ticket_id, kind, request_text, lang, model_category, model_priority, corrected_category, corrected_priority, note, author_alias, author_role, created_at";

/** Past corrections, newest first (staff and admin only, by RLS). */
export async function listHints(sb: Sb, limit = 200): Promise<HintRow[]> {
  return unwrap(await sb.from("ticket_hints").select(HINT_COLUMNS).order("created_at", { ascending: false }).limit(limit)) as HintRow[];
}
