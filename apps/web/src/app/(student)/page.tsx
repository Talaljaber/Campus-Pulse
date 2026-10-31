import { redirect } from "next/navigation";
import { ChatScreen } from "@/components/chat/ChatScreen";
import { fetchProfile } from "@/lib/auth/profile";
import { createServerSupabase } from "@/lib/supabase/server";

/**
 * `/`: the student chat. The proxy already sends signed-out users to `/login`; the check
 * here is the second lock, and it supplies the alias for the live notifications.
 */
export default async function StudentHome() {
  const sb = await createServerSupabase();
  const { data } = await sb.auth.getUser();
  if (!data.user) redirect("/login");
  const profile = await fetchProfile(sb, data.user.id);
  if (!profile) redirect("/login");
  return <ChatScreen alias={profile.alias} />;
}
