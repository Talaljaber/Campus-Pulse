import type { DictKey } from "@/i18n";
import type { IconName } from "@/components/ui/Icon";
import type { Role } from "@/lib/auth/routing";

/** Every top-level tab of the portal shell. */
export type TabId =
  | "home"
  | "ask"
  | "requests"
  | "profile"
  | "queue"
  | "announcements"
  | "incidents"
  | "corrections"
  | "accounts"
  | "reports";

/** A page the shell can mark as current: a tab, or the Outbox tile that admins have instead of a tab. */
export type PageId = TabId | "outbox";

export interface TabSpec {
  id: TabId;
  href: string;
  labelKey: DictKey;
  icon: IconName;
}

export interface TileDef {
  id: PageId;
  href: string;
  icon: IconName;
  labelKey: DictKey;
}

const TAB: Record<TabId, TabSpec> = {
  home: { id: "home", href: "/", labelKey: "nav.home", icon: "home" },
  ask: { id: "ask", href: "/ask", labelKey: "nav.ask", icon: "chat" },
  requests: { id: "requests", href: "/requests", labelKey: "nav.requests", icon: "ticket" },
  profile: { id: "profile", href: "/profile", labelKey: "nav.profile", icon: "user" },
  queue: { id: "queue", href: "/staff", labelKey: "nav.queue", icon: "briefcase" },
  announcements: { id: "announcements", href: "/staff/announcements", labelKey: "nav.announcements", icon: "megaphone" },
  incidents: { id: "incidents", href: "/pulse", labelKey: "nav.incidents", icon: "map" },
  corrections: { id: "corrections", href: "/staff/reviews", labelKey: "nav.corrections", icon: "check" },
  accounts: { id: "accounts", href: "/admin/accounts", labelKey: "nav.accounts", icon: "user" },
  reports: { id: "reports", href: "/lab", labelKey: "nav.reports", icon: "flask" },
};

const STUDENT_TABS: readonly TabId[] = ["home", "ask", "requests", "profile"];
const STAFF_TABS: readonly TabId[] = ["queue", "ask", "announcements", "incidents", "corrections"];
// Reports (the model lab, /lab) is hidden from the tab bar for now (user decision 2026-11-06); the page still
// works at /lab. To bring it back, restore "reports" in the list below.
const ADMIN_TABS: readonly TabId[] = [...STAFF_TABS, "accounts" /* , "reports" */];

/** The tabs a role sees, in display order. Only what the role may open, so no link ever bounces. */
export function tabsFor(role: Role): TabSpec[] {
  const ids = role === "admin" ? ADMIN_TABS : role === "staff" ? STAFF_TABS : STUDENT_TABS;
  return ids.map((id) => TAB[id]);
}

const REQUESTS_TILE: TileDef = { id: "requests", href: "/requests", icon: "ticket", labelKey: "nav.requests" };
const OUTBOX_TILE: TileDef = { id: "outbox", href: "/outbox", icon: "mail", labelKey: "nav.outbox" };

/**
 * Pages that staff and admins reach from Profile because they are not in the tab bar: their own
 * requests, and for admins the outbox. Students have My requests as a tab, so they get none.
 */
export function tilesFor(role: Role): TileDef[] {
  if (role === "student") return [];
  return role === "admin" ? [REQUESTS_TILE, OUTBOX_TILE] : [REQUESTS_TILE];
}

/** Label key for the breadcrumb's last item: the tab's own label, or the outbox. */
export function labelKeyOf(id: PageId): DictKey {
  return id === "outbox" ? "nav.outbox" : TAB[id].labelKey;
}
