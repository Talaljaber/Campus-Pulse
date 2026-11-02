import { redirect } from "next/navigation";
import { AdvisorScreen } from "@/components/staff/AdvisorScreen";
import { fetchProfile, nameOf } from "@/lib/auth/profile";
import { homeFor } from "@/lib/auth/routing";
import { createServerSupabase } from "@/lib/supabase/server";

/**
 * `/staff/reviews`: the advisor's review queue (UD-13). The proxy keeps students and signed-out
 * visitors out of `/staff/*`; this is the second lock, and it supplies the office. Which items
 * appear is decided by the AI service from the caller's verified session, never by this page.
 */
export default async function AdvisorReviewsPage() {
  const sb = await createServerSupabase();
  const { data } = await sb.auth.getUser();
  if (!data.user) redirect("/login");
  const profile = await fetchProfile(sb, data.user.id);
  if (!profile) redirect("/login");
  if (profile.role === "student") redirect(homeFor(profile.role));
  return <AdvisorScreen role={profile.role} alias={profile.alias} name={nameOf(profile)} office={profile.role === "staff" ? profile.office : null} />;
}
