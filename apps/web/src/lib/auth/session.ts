import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { supabaseEnv } from "../supabase/env";
import type { Database } from "../supabase/types";
import { fetchProfile } from "./profile";
import type { Role } from "./routing";

export interface SessionInfo {
  role: Role | null;
  /** The response to continue with (carries refreshed auth cookies). */
  response: NextResponse;
}

/**
 * Verifies the session for a page request and refreshes it when the access token is
 * about to expire (`@supabase/ssr` writes the new cookies into the response). The user is
 * checked with `getUser()`, which asks Supabase, rather than trusting the cookie contents.
 * The role comes from the user's own `profiles` row.
 */
export async function readSession(request: NextRequest): Promise<SessionInfo> {
  let response = NextResponse.next({ request });
  const { url, anonKey } = supabaseEnv();
  const sb = createServerClient<Database>(url, anonKey, {
    cookies: {
      getAll: () => request.cookies.getAll(),
      setAll: (list) => {
        for (const c of list) request.cookies.set(c.name, c.value);
        response = NextResponse.next({ request });
        for (const c of list) response.cookies.set(c.name, c.value, c.options);
      },
    },
  });
  const { data } = await sb.auth.getUser();
  if (!data.user) return { role: null, response };
  const profile = await fetchProfile(sb, data.user.id);
  return { role: profile?.role ?? null, response };
}

/** Copies the refreshed auth cookies onto a redirect so a token refresh is not lost. */
export function carryCookies(from: NextResponse, to: NextResponse): NextResponse {
  for (const c of from.cookies.getAll()) to.cookies.set(c);
  return to;
}
