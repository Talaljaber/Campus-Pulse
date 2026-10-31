import type { DictKey } from "@/i18n";
import type { Role } from "./routing";

/**
 * The three seeded demo logins (D-008). Emails only: the shared password is typed by the
 * presenter and never appears in code, env defaults or the repository.
 */
export const DEMO_ACCOUNTS: readonly { role: Role; email: string; labelKey: DictKey }[] = [
  { role: "student", email: "talal@demo.local", labelKey: "auth.demoStudent" },
  { role: "staff", email: "it@demo.local", labelKey: "auth.demoStaff" },
  { role: "admin", email: "admin@demo.local", labelKey: "auth.demoAdmin" },
];
