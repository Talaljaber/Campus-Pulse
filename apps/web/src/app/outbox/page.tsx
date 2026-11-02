import { redirect } from "next/navigation";
import { OutboxScreen } from "@/components/outbox/OutboxScreen";
import { fetchProfile, nameOf } from "@/lib/auth/profile";
import { homeFor } from "@/lib/auth/routing";
import { createServerSupabase } from "@/lib/supabase/server";

/**
 * `/outbox`: every message the system tried to send, for staff and admin. The proxy already keeps
 * everyone else out; this is the second lock. Row-level security decides which rows are readable.
 */
export default async function OutboxPage() {
  const sb = await createServerSupabase();
  const { data } = await sb.auth.getUser();
  if (!data.user) redirect("/login");
  const profile = await fetchProfile(sb, data.user.id);
  if (!profile) redirect("/login");
  if (profile.role === "student") redirect(homeFor(profile.role));
  return <OutboxScreen role={profile.role} alias={profile.alias} name={nameOf(profile)} />;
}
