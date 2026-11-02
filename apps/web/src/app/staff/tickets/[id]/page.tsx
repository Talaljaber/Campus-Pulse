import { TicketWorkspace } from "@/components/staff/TicketWorkspace";
import { requireProfile } from "@/lib/auth/guard";

/**
 * `/staff/tickets/[id]`: the ticket workspace for staff and admin. The proxy and `requireProfile` keep
 * everyone else out; which ticket the caller may open is decided by row-level security, and a staff
 * member's own request counts as not found.
 */
export default async function StaffTicketPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const profile = await requireProfile(["staff", "admin"]);
  return <TicketWorkspace ticketId={id} role={profile.role === "admin" ? "admin" : "staff"} alias={profile.alias} />;
}
