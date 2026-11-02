import { PlaceholderScreen } from "@/components/shell/PlaceholderScreen";
import { requireProfile } from "@/lib/auth/guard";

/** `/profile`: the profile page (placeholder until the accounts package lands), for every signed-in role. */
export default async function ProfilePage() {
  const profile = await requireProfile();
  return <PlaceholderScreen role={profile.role} alias={profile.alias} current="profile" />;
}
