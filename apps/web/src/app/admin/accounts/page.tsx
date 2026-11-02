import { PlaceholderScreen } from "@/components/shell/PlaceholderScreen";
import { requireProfile } from "@/lib/auth/guard";

/** `/admin/accounts`: account overview for admins (placeholder). The proxy and this check both require admin. */
export default async function AdminAccountsPage() {
  const profile = await requireProfile(["admin"]);
  return <PlaceholderScreen role={profile.role} alias={profile.alias} current="accounts" />;
}
