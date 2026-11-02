"use client";

import { useT } from "@/i18n";
import type { Role } from "@/lib/auth/routing";
import type { ProfileRow } from "@/lib/profiles/types";
import { AppShell } from "../shell/AppShell";
import { PageHeader } from "../shell/PageHeader";
import { useOfficeLabel } from "../staff/office";
import { InfoGrid, InfoPanel, type InfoRow } from "../ui/InfoPanel";

/** Props for {@link ProfileScreen}. */
export interface ProfileScreenProps {
  role: Role;
  profile: ProfileRow;
}

/** Profile `/profile`: a read-only list of the fictional account data, with the "simulated account" note. */
export function ProfileScreen({ role, profile }: ProfileScreenProps) {
  const t = useT();
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
  return (
    <AppShell role={role} current="profile" name={name} alias={profile.alias}>
      <PageHeader title={t("nav.profile")} />
      <InfoPanel title={t("profile.panel")}>
        <InfoGrid rows={rows} />
      </InfoPanel>
      <p className="border border-line-strong border-s-[6px] border-s-orange bg-surface-1 p-3 text-fg-1">{t("profile.simulated")}</p>
    </AppShell>
  );
}
