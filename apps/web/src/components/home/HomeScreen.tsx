"use client";

import { useT } from "@/i18n";
import type { Role } from "@/lib/auth/routing";
import { AppShell } from "../shell/AppShell";
import { PageHeader } from "../shell/PageHeader";
import { EmptyState } from "../ui/EmptyState";

/** Props for {@link HomeScreen}. */
export interface HomeScreenProps {
  role: Role;
  /** Shown as the name until profiles carry a display name. */
  alias: string | null;
}

/** Home placeholder: the welcome heading and an empty announcements area (the announcements package fills it). */
export function HomeScreen({ role, alias }: HomeScreenProps) {
  const t = useT();
  return (
    <AppShell role={role} current="home" alias={alias}>
      <PageHeader title={t("home.welcome", { name: alias ?? "" }).trim()} />
      <EmptyState title={t("home.announcementsEmpty")} />
    </AppShell>
  );
}
