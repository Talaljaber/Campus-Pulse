import "server-only";
import { redirect } from "next/navigation";
import { createServerSupabase } from "@/lib/supabase/server";
import { fetchProfile, type Profile } from "./profile";
import { homeFor, type Role } from "./routing";

/**
 * The second lock every page applies after the proxy: a session, a profile, and (when `allowed` is
 * given) a role from that list. Signed-out or profile-less visitors go to `/login`; a role that is
 * not allowed goes to its own home. Returns the caller's profile.
 */
export async function requireProfile(allowed?: readonly Role[]): Promise<Profile> {
  const sb = await createServerSupabase();
  const { data } = await sb.auth.getUser();
  if (!data.user) redirect("/login");
  const profile = await fetchProfile(sb, data.user.id);
  if (!profile) redirect("/login");
  if (allowed && !allowed.includes(profile.role)) redirect(homeFor(profile.role));
  return profile;
}
