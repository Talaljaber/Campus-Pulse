import type { Sb } from "../supabase/types";
import { isRole, type Role } from "./routing";

export interface Profile {
  id: string;
  role: Role;
  /** Office code (`it`, `registrar`, ...) for staff; null for students and admins. */
  office: string | null;
  /** The pseudonymous alias the AI service and Realtime filters use. */
  alias: string | null;
  /** The fictional full name shown in the header and on Profile; null when the row has none. */
  displayName: string | null;
}

/** The name the header and Home greet: the display name, else the alias. */
export function nameOf(profile: Pick<Profile, "displayName" | "alias">): string | null {
  return profile.displayName?.trim() || profile.alias;
}

/**
 * Reads the caller's own `profiles` row (RLS: you can read yours). Returns null when the
 * row is missing or carries an unknown role, so callers treat the user as not set up.
 */
export async function fetchProfile(sb: Sb, userId: string): Promise<Profile | null> {
  const { data, error } = await sb.from("profiles").select("id, role, office, alias, display_name").eq("id", userId).maybeSingle();
  if (error || !data || !isRole(data.role)) return null;
  return { id: data.id, role: data.role, office: data.office, alias: data.alias, displayName: data.display_name };
}
