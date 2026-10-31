import { redirect } from "next/navigation";
import { PulseScreen } from "@/components/pulse/PulseScreen";
import { fetchProfile } from "@/lib/auth/profile";
import { homeFor } from "@/lib/auth/routing";
import { createServerSupabase } from "@/lib/supabase/server";

/**
 * `/pulse`: the live campus map, incidents and feed for staff and admin. The proxy already
 * keeps everyone else out; this is the second lock.
 */
export default async function PulsePage() {
  const sb = await createServerSupabase();
  const { data } = await sb.auth.getUser();
  if (!data.user) redirect("/login");
  const profile = await fetchProfile(sb, data.user.id);
  if (!profile) redirect("/login");
  if (profile.role === "student") redirect(homeFor(profile.role));
  return <PulseScreen />;
}
