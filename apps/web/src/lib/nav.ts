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
}

export interface TileDef {
  id: PageId;
  href: string;
  icon: IconName;
  labelKey: DictKey;
}

const TAB: Record<TabId, TabSpec> = {
  home: { id: "home", href: "/", labelKey: "nav.home" },
  ask: { id: "ask", href: "/ask", labelKey: "nav.ask" },
  requests: { id: "requests", href: "/requests", labelKey: "nav.requests" },
  profile: { id: "profile", href: "/profile", labelKey: "nav.profile" },
  queue: { id: "queue", href: "/staff", labelKey: "nav.queue" },
  announcements: { id: "announcements", href: "/staff/announcements", labelKey: "nav.announcements" },
  incidents: { id: "incidents", href: "/pulse", labelKey: "nav.incidents" },
  corrections: { id: "corrections", href: "/staff/reviews", labelKey: "nav.corrections" },
  accounts: { id: "accounts", href: "/admin/accounts", labelKey: "nav.accounts" },
  reports: { id: "reports", href: "/lab", labelKey: "nav.reports" },
};

const STUDENT_TABS: readonly TabId[] = ["home", "ask", "requests", "profile"];
const STAFF_TABS: readonly TabId[] = ["queue", "announcements", "incidents", "corrections"];
const ADMIN_TABS: readonly TabId[] = [...STAFF_TABS, "accounts", "reports"];

/** The tabs a role sees, in display order. Only what the role may open, so no link ever bounces. */
export function tabsFor(role: Role): TabSpec[] {
  const ids = role === "admin" ? ADMIN_TABS : role === "staff" ? STAFF_TABS : STUDENT_TABS;
  return ids.map((id) => TAB[id]);
}

const ASK_TILE: TileDef = { id: "ask", href: "/ask", icon: "chat", labelKey: "nav.askForHelp" };
const REQUESTS_TILE: TileDef = { id: "requests", href: "/requests", icon: "ticket", labelKey: "nav.requests" };
const OUTBOX_TILE: TileDef = { id: "outbox", href: "/outbox", icon: "mail", labelKey: "nav.outbox" };

/** The icon-tile row under the tabs. Students have none; staff use the agent and track their own requests; admin adds the outbox. */
export function tilesFor(role: Role): TileDef[] {
  if (role === "student") return [];
  return role === "admin" ? [ASK_TILE, REQUESTS_TILE, OUTBOX_TILE] : [ASK_TILE, REQUESTS_TILE];
}

/** Label key for the breadcrumb's last item: the tab's own label, or the outbox. */
export function labelKeyOf(id: PageId): DictKey {
  return id === "outbox" ? "nav.outbox" : TAB[id].labelKey;
}
