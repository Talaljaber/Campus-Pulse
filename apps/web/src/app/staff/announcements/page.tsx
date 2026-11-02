import { PlaceholderScreen } from "@/components/shell/PlaceholderScreen";
import { requireProfile } from "@/lib/auth/guard";

/** `/staff/announcements`: staff and admin announcements (placeholder until the announcements package lands). */
export default async function StaffAnnouncementsPage() {
  const profile = await requireProfile(["staff", "admin"]);
  return <PlaceholderScreen role={profile.role} alias={profile.alias} current="announcements" />;
}
