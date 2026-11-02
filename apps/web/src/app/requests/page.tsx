import { MyRequestsScreen } from "@/components/requests/MyRequestsScreen";
import { requireProfile } from "@/lib/auth/guard";

/** `/requests`: My requests, for every signed-in role (the tickets this person opened). */
export default async function RequestsPage() {
  const profile = await requireProfile();
  return <MyRequestsScreen role={profile.role} alias={profile.alias} />;
}
