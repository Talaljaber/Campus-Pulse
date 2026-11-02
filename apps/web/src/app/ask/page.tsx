import { AgentScreen } from "@/components/chat/AgentScreen";
import { requireProfile } from "@/lib/auth/guard";

/**
 * `/ask`: the request assistant, for every signed-in role. The proxy already sends signed-out visitors
 * to `/login`; the check here is the second lock, and it supplies the alias for the shell.
 */
export default async function AskPage() {
  const profile = await requireProfile();
  return <AgentScreen alias={profile.alias} role={profile.role} />;
}
