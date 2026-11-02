import { AccountsScreen } from "@/components/accounts/AccountsScreen";
import { requireProfile } from "@/lib/auth/guard";
import { nameOf } from "@/lib/auth/profile";
import { listProfiles } from "@/lib/repos/profiles";
import { createServerSupabase } from "@/lib/supabase/server";

/** `/admin/accounts`: read-only table of the (fictional) accounts. The proxy and this check both require admin. */
export default async function AdminAccountsPage() {
  const profile = await requireProfile(["admin"]);
  const rows = await listProfiles(await createServerSupabase());
  return <AccountsScreen alias={profile.alias} name={nameOf(profile)} rows={rows} />;
}
