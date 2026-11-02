import { ProfileScreen } from "@/components/profile/ProfileScreen";
import { requireProfile } from "@/lib/auth/guard";
import { getMyProfile } from "@/lib/repos/profiles";
import { createServerSupabase } from "@/lib/supabase/server";

/** `/profile`: the caller's read-only (fictional) account data, for every signed-in role. */
export default async function ProfilePage() {
  const mine = await requireProfile();
  const row = await getMyProfile(await createServerSupabase(), mine.id);
  return (
    <ProfileScreen
      role={mine.role}
      profile={row ?? { id: mine.id, role: mine.role, office: mine.office, alias: mine.alias, display_name: mine.displayName, student_number: null, faculty: null, university_email: null }}
    />
  );
}
