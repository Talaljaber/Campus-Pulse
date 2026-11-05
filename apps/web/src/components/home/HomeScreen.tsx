"use client";

import { useLiveAnnouncements } from "@/hooks/useAnnouncements";
import { useT } from "@/i18n";
import type { Role } from "@/lib/auth/routing";
import { AnnouncementList } from "../announcements/AnnouncementList";
import { AppShell } from "../shell/AppShell";
import { PageHeader } from "../shell/PageHeader";
import { Loadable } from "../ui/Loadable";

/** Props for {@link HomeScreen}. */
export interface HomeScreenProps {
  role: Role;
  /** The signed-in alias. */
  alias: string | null;
  /** The fictional display name. */
  name?: string | null;
}

/**
 * Home `/`: the live announcements (kept current with Realtime). Asking and tracking requests are
 * tabs, so the page has no greeting or shortcut tiles.
 */
export function HomeScreen({ role, alias, name = null }: HomeScreenProps) {
  const t = useT();
  const announcements = useLiveAnnouncements();
  return (
    <AppShell role={role} current="home" name={name} alias={alias}>
      <PageHeader title={t("home.announcements")} />
      <section aria-label={t("home.announcements")} className="flex flex-col gap-3">
        <Loadable state={announcements.load} onRetry={announcements.reload} lines={3}>
          <AnnouncementList rows={announcements.rows} compact />
        </Loadable>
      </section>
    </AppShell>
  );
}
