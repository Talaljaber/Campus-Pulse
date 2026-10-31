import { createBrowserClient } from "@supabase/ssr";
import { supabaseEnv } from "./env";
import type { Database, Sb } from "./types";

let cached: Sb | null = null;

/**
 * The browser Supabase client (anon key, the signed-in user's session from cookies).
 * One instance per tab. Every read goes through RLS; there are no write policies for
 * clients, so writes happen through the AI proxy only.
 */
export function createBrowserSupabase(): Sb {
  if (!cached) {
    const { url, anonKey } = supabaseEnv();
    cached = createBrowserClient<Database>(url, anonKey);
  }
  return cached;
}
