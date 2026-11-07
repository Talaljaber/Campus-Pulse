import { AdminOverview } from "@/components/admin/AdminOverview";
import { fetchOverview, periodOf, type Overview } from "@/lib/admin/overview";
import { requireProfile } from "@/lib/auth/guard";
import { nameOf } from "@/lib/auth/profile";
import { createServerSupabase } from "@/lib/supabase/server";

/**
 * `/admin`: the administrator's home (P10.17). The proxy and this check both require admin, and the
 * database function behind the numbers refuses anyone else a third time.
 */
export default async function AdminPage({ searchParams }: { searchParams: Promise<{ days?: string | string[] }> }) {
  const profile = await requireProfile(["admin"]);
  const period = periodOf((await searchParams).days);
  let overview: Overview | null = null;
  try {
    overview = await fetchOverview(await createServerSupabase(), period);
  } catch {
    overview = null; // the screen shows "could not load" instead of an error page
  }
  return <AdminOverview alias={profile.alias} name={nameOf(profile)} period={period} overview={overview} />;
}
