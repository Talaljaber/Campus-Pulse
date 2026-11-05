"use client";

import { useSignOut } from "@/hooks/useSignIn";
import { useT } from "@/i18n";
import type { Role } from "@/lib/auth/routing";
import { tilesFor } from "@/lib/nav";
import type { ProfileRow } from "@/lib/profiles/types";
import { AppShell } from "../shell/AppShell";
import { PageHeader } from "../shell/PageHeader";
import { TileRow } from "../shell/TileRow";
import { useOfficeLabel } from "../staff/office";
import { Button } from "../ui/Button";
import { InfoGrid, InfoPanel, type InfoRow } from "../ui/InfoPanel";
import { Icon } from "../ui/Icon";
import { LanguageSwitch } from "../ui/LanguageSwitch";
import { NotificationEmailPanel } from "./NotificationEmailPanel";

/** Props for {@link ProfileScreen}. */
export interface ProfileScreenProps {
  role: Role;
  profile: ProfileRow;
}

/**
 * Profile `/profile`: the fictional account data, the notification email, the language switch and
 * Sign out. Staff and admins also get shortcuts to the pages that are not in their tab bar (their own
 * requests, and for admins the outbox).
 */
export function ProfileScreen({ role, profile }: ProfileScreenProps) {
  const t = useT();
  const signOut = useSignOut();
  const officeLabel = useOfficeLabel();
  const dash = t("common.none");
  const name = profile.display_name?.trim() || profile.alias || dash;
  const rows: InfoRow[] = [
    { label: t("profile.name"), value: name },
    ...(role === "student"
      ? [
          { label: t("profile.studentNumber"), value: profile.student_number ?? dash },
          { label: t("profile.faculty"), value: profile.faculty ?? dash },
        ]
      : []),
    { label: t("profile.email"), value: <span dir="ltr">{profile.university_email ?? dash}</span> },
    { label: t("profile.role"), value: t(`profile.roles.${role}`) },
    ...(role === "staff" ? [{ label: t("profile.office"), value: profile.office ? officeLabel(profile.office) : dash }] : []),
  ];
  const shortcuts = tilesFor(role).map((d) => ({ id: d.id, icon: d.icon, href: d.href, label: t(d.labelKey) }));
  return (
    <AppShell role={role} current="profile" name={name} alias={profile.alias}>
      <PageHeader title={t("nav.profile")} />
      <TileRow tiles={shortcuts} label={t("shell.shortcuts")} />
      <InfoPanel title={t("profile.panel")}>
        <InfoGrid rows={rows} />
      </InfoPanel>
      <NotificationEmailPanel />
      <InfoPanel title={t("profile.settings")}>
        <div className="flex flex-wrap items-center gap-3">
          <LanguageSwitch />
          <Button variant="secondary" onClick={() => void signOut()} className="gap-2">
            <Icon name="logout" size={18} strokeWidth={1.8} />
            {t("auth.signOut")}
          </Button>
        </div>
      </InfoPanel>
      <p className="border border-line-strong border-s-[6px] border-s-orange bg-surface-1 p-3 text-fg-1">{t("profile.simulated")}</p>
    </AppShell>
  );
}
