"use client";

import { useLiveAnnouncements } from "@/hooks/useAnnouncements";
import { useT } from "@/i18n";
import { firstName } from "@/lib/announcements/view";
import type { Role } from "@/lib/auth/routing";
import { AnnouncementList } from "../announcements/AnnouncementList";
import { AppShell, type TileSpec } from "../shell/AppShell";
import { PageHeader } from "../shell/PageHeader";
import { Loadable } from "../ui/Loadable";

/** Props for {@link HomeScreen}. */
export interface HomeScreenProps {
  role: Role;
  /** The signed-in alias (the header name falls back to it). */
  alias: string | null;
  /** The fictional display name; the greeting uses its first word. */
  name?: string | null;
}

/**
 * Home `/`: "Welcome, <first name>", the live announcements (kept current with Realtime) and, for a
 * student, two tiles: ask a question and my requests. Staff and admins keep their own shortcut tiles.
 */
export function HomeScreen({ role, alias, name = null }: HomeScreenProps) {
  const t = useT();
  const announcements = useLiveAnnouncements();
  const shown = name ?? alias;
  const tiles: TileSpec[] | undefined =
    role === "student"
      ? [
          { id: "ask", icon: "chat", href: "/ask", label: t("home.tileAsk"), hint: t("home.tileAskHint") },
          { id: "requests", icon: "ticket", href: "/requests", label: t("nav.requests"), hint: t("home.tileRequestsHint") },
        ]
      : undefined;
  return (
    <AppShell role={role} current="home" name={shown} alias={alias} tiles={tiles}>
      <PageHeader title={t("home.welcome", { name: firstName(shown) }).trim()} />
      <section aria-labelledby="home-announcements" className="flex flex-col gap-3">
        <h2 id="home-announcements" className="text-xl font-bold text-accent">
          {t("home.announcements")}
        </h2>
        <Loadable state={announcements.load} onRetry={announcements.reload} lines={3}>
          <AnnouncementList rows={announcements.rows} />
        </Loadable>
      </section>
    </AppShell>
  );
}
