"use client";

import { useT } from "@/i18n";
import type { Role } from "@/lib/auth/routing";
import type { PageId } from "@/lib/nav";
import { labelKeyOf } from "@/lib/nav";
import { EmptyState } from "../ui/EmptyState";
import { AppShell } from "./AppShell";
import { PageHeader } from "./PageHeader";

/** Props for {@link PlaceholderScreen}. */
export interface PlaceholderScreenProps {
  role: Role;
  alias: string | null;
  /** The tab this page belongs to; its label is the page title. */
  current: PageId;
}

/** A page whose package has not landed yet: the shell, the title and a "Coming in this build" note. */
export function PlaceholderScreen({ role, alias, current }: PlaceholderScreenProps) {
  const t = useT();
  return (
    <AppShell role={role} current={current} alias={alias}>
      <PageHeader title={t(labelKeyOf(current))} />
      <EmptyState title={t("shell.comingSoon")} />
    </AppShell>
  );
}
