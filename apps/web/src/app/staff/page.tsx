import { redirect } from "next/navigation";
import { StaffScreen } from "@/components/staff/StaffScreen";
import { fetchProfile } from "@/lib/auth/profile";
import { homeFor } from "@/lib/auth/routing";
import { createServerSupabase } from "@/lib/supabase/server";

/**
 * `/staff`: the staff dashboard. The proxy already keeps students and signed-out visitors
 * out; this is the second lock, and it supplies the office. An admin has no office and sees
 * every office (row-level security decides, not this page).
 */
export default async function StaffPage() {
  const sb = await createServerSupabase();
  const { data } = await sb.auth.getUser();
  if (!data.user) redirect("/login");
  const profile = await fetchProfile(sb, data.user.id);
  if (!profile) redirect("/login");
  if (profile.role === "student") redirect(homeFor(profile.role));
  return <StaffScreen role={profile.role} alias={profile.alias} office={profile.role === "staff" ? profile.office : null} />;
}
