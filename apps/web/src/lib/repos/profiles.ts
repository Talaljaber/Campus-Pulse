import type { Sb, Tables } from "../supabase/types";
import { unwrap } from "./realtime";

/** The columns the portal reads. `demo_inbox` is never selected: it is delivery plumbing, not profile data. */
const COLUMNS = "id, role, office, alias, display_name, student_number, faculty, university_email";

export type ProfileRow = Pick<
  Tables<"profiles">,
  "id" | "role" | "office" | "alias" | "display_name" | "student_number" | "faculty" | "university_email"
>;

/** The caller's own profile row (RLS: you can read yours). Null when there is none. */
export async function getMyProfile(sb: Sb, userId: string): Promise<ProfileRow | null> {
  const { data, error } = await sb.from("profiles").select(COLUMNS).eq("id", userId).maybeSingle();
  if (error) throw new Error(error.message);
  return data;
}

/** Every profile, for the admin Accounts table (RLS lets only admins read all rows). Ordered by role, then name. */
export async function listProfiles(sb: Sb): Promise<ProfileRow[]> {
  return unwrap(await sb.from("profiles").select(COLUMNS).order("role").order("display_name", { nullsFirst: false }));
}
