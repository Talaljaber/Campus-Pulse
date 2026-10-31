/**
 * Thin re-export of the generated `Database` type. The file itself belongs to the DB
 * stream (`supabase/types/database.types.ts`) and is never copied or edited here.
 * Type-only, so nothing is bundled.
 */
import type { SupabaseClient } from "@supabase/supabase-js";
import type { Database } from "@db/database.types";

export type { Database, Json, Tables } from "@db/database.types";

/** The client type every repo takes: browser, server and test doubles all satisfy it. */
export type Sb = SupabaseClient<Database>;
