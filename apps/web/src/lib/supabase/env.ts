/**
 * Public Supabase settings. Only the URL and the anon (publishable) key exist in the
 * web app; the service-role key is never present here. The `process.env.NEXT_PUBLIC_*`
 * reads must stay literal so Next can inline them into the client bundle.
 */
export interface SupabaseEnv {
  url: string;
  anonKey: string;
}

/** Reads the public settings. Throws a clear error when they are missing. */
export function supabaseEnv(): SupabaseEnv {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anonKey) {
    throw new Error("NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY must be set.");
  }
  return { url, anonKey };
}
