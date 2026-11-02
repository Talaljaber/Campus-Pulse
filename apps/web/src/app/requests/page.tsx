import { PlaceholderScreen } from "@/components/shell/PlaceholderScreen";
import { requireProfile } from "@/lib/auth/guard";

/** `/requests`: My requests (placeholder until the tickets package lands), for every signed-in role. */
export default async function RequestsPage() {
  const profile = await requireProfile();
  return <PlaceholderScreen role={profile.role} alias={profile.alias} current="requests" />;
}
