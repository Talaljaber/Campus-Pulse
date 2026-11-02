import { RequestScreen } from "@/components/requests/RequestScreen";
import { requireProfile } from "@/lib/auth/guard";
import { nameOf } from "@/lib/auth/profile";

/** `/requests/[id]`: one of the caller's own requests. Anyone else's ticket shows "not found". */
export default async function RequestPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const profile = await requireProfile();
  return <RequestScreen ticketId={id} role={profile.role} alias={profile.alias} name={nameOf(profile)} />;
}
