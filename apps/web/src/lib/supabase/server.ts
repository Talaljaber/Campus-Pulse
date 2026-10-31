import "server-only";
import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { supabaseEnv } from "./env";
import type { Database, Sb } from "./types";

/**
 * A Supabase client for Server Components and route handlers, bound to the request's
 * cookies. Token refresh is written by `src/proxy.ts`; writing cookies from a Server
 * Component throws, so that case is ignored on purpose.
 */
export async function createServerSupabase(): Promise<Sb> {
  const jar = await cookies();
  const { url, anonKey } = supabaseEnv();
  return createServerClient<Database>(url, anonKey, {
    cookies: {
      getAll: () => jar.getAll(),
      setAll: (list) => {
        try {
          for (const c of list) jar.set(c.name, c.value, c.options);
        } catch {
          // Server Component: the proxy already refreshed the session.
        }
      },
    },
  });
}
