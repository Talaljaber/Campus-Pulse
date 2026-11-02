import { redirect } from "next/navigation";
import { LabScreen } from "@/components/lab/LabScreen";
import { fetchProfile, nameOf } from "@/lib/auth/profile";
import { homeFor } from "@/lib/auth/routing";
import { createServerSupabase } from "@/lib/supabase/server";

/**
 * `/lab`: the model lab, admin only. The proxy already sends staff and students to their own home
 * and signed-out visitors to `/login`; this is the second lock. The API checks the role again on
 * every call, so a forged client could not read the metrics either.
 */
export default async function LabPage() {
  const sb = await createServerSupabase();
  const { data } = await sb.auth.getUser();
  if (!data.user) redirect("/login");
  const profile = await fetchProfile(sb, data.user.id);
  if (!profile) redirect("/login");
  if (profile.role !== "admin") redirect(homeFor(profile.role));
  return <LabScreen alias={profile.alias} name={nameOf(profile)} />;
}
