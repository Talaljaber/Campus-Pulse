import { ChatScreen } from "@/components/chat/ChatScreen";
import { requireProfile } from "@/lib/auth/guard";

/**
 * `/ask`: the request chat, for every signed-in role. The proxy already sends signed-out visitors
 * to `/login`; the check here is the second lock, and it supplies the alias for live notifications.
 */
export default async function AskPage() {
  const profile = await requireProfile();
  return <ChatScreen alias={profile.alias} role={profile.role} />;
}
