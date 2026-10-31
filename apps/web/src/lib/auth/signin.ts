import type { Sb } from "../supabase/types";
import { fetchProfile } from "./profile";
import { homeFor, safeNext, type Role } from "./routing";

export type SignInResult =
  | { ok: true; role: Role; destination: string }
  | { ok: false; reason: "invalid" | "no_profile" | "network" };

/**
 * Email and password sign-in, then role routing. `next` (from `?next=`) is honoured only
 * when it is a same-origin path. Whether the role may open it is decided by the proxy on
 * the next request, which redirects to the role's home otherwise.
 */
export async function signIn(sb: Sb, email: string, password: string, next?: string | null): Promise<SignInResult> {
  let res;
  try {
    res = await sb.auth.signInWithPassword({ email: email.trim(), password });
  } catch {
    return { ok: false, reason: "network" };
  }
  if (res.error || !res.data.user) {
    // Supabase answers 400 for bad credentials; anything without a status is a transport problem.
    return { ok: false, reason: res.error?.status && res.error.status < 500 ? "invalid" : "network" };
  }
  const profile = await fetchProfile(sb, res.data.user.id);
  if (!profile) {
    await sb.auth.signOut();
    return { ok: false, reason: "no_profile" };
  }
  return { ok: true, role: profile.role, destination: safeNext(next, homeFor(profile.role)) };
}

/** Ends the session (clears the cookies through the browser client). */
export async function signOut(sb: Sb): Promise<void> {
  await sb.auth.signOut();
}
