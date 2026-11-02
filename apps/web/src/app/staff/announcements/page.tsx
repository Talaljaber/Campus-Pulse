import { StaffAnnouncements } from "@/components/announcements/StaffAnnouncements";
import { requireProfile } from "@/lib/auth/guard";
import { nameOf } from "@/lib/auth/profile";

/** `/staff/announcements`: staff post and archive announcements for their office; an admin for any office. */
export default async function StaffAnnouncementsPage() {
  const profile = await requireProfile(["staff", "admin"]);
  return (
    <StaffAnnouncements
      role={profile.role === "admin" ? "admin" : "staff"}
      alias={profile.alias}
      name={nameOf(profile)}
      office={profile.role === "staff" ? profile.office : null}
    />
  );
}
