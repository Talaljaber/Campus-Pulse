import { HomeScreen } from "@/components/home/HomeScreen";
import { requireProfile } from "@/lib/auth/guard";
import { nameOf } from "@/lib/auth/profile";

/**
 * `/`: Home (welcome and the live announcements) for every signed-in role. The proxy already sends
 * signed-out visitors to `/login`; the check here is the second lock.
 */
export default async function HomePage() {
  const profile = await requireProfile();
  return <HomeScreen role={profile.role} alias={profile.alias} name={nameOf(profile)} />;
}
