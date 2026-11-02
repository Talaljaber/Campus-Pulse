import type { Role } from "./routing";

/**
 * The seeded demo logins (fictional people, all `<username>@demo.local`). Usernames only: the shared
 * password is typed by the presenter and never appears in code, env defaults or the repository.
 */
export const DEMO_ACCOUNTS: readonly { username: string; role: Role }[] = [
  { username: "talal", role: "student" },
  { username: "lina", role: "student" },
  { username: "omar", role: "student" },
  { username: "registrar", role: "staff" },
  { username: "it", role: "staff" },
  { username: "finance", role: "staff" },
  { username: "transport", role: "staff" },
  { username: "facilities", role: "staff" },
  { username: "academic", role: "staff" },
  { username: "admin", role: "admin" },
];

/** The login email for a typed username: a bare name becomes `<name>@demo.local`; an address is kept. */
export function toLoginEmail(username: string): string {
  const u = username.trim();
  return u.includes("@") ? u : `${u}@demo.local`;
}
