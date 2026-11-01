import type { DictKey } from "@/i18n";
import type { Role } from "./routing";

/**
 * The three seeded demo logins (D-008). Emails only: the shared password is typed by the
 * presenter and never appears in code, env defaults or the repository.
 */
export const DEMO_ACCOUNTS: readonly { id: string; role: Role; email: string; labelKey: DictKey }[] = [
  { id: "student", role: "student", email: "talal@demo.local", labelKey: "auth.demoStudent" },
  { id: "staff", role: "staff", email: "it@demo.local", labelKey: "auth.demoStaff" },
  // The fictional Dr. Rana Haddad: staff of the academic office, who lands on the review queue (UD-13).
  { id: "advisor", role: "staff", email: "advisor@demo.local", labelKey: "auth.demoAdvisor" },
  { id: "admin", role: "admin", email: "admin@demo.local", labelKey: "auth.demoAdmin" },
];
