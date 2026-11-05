"use client";

import Link from "next/link";
import { useState } from "react";
import { useT } from "@/i18n";
import type { Role } from "@/lib/auth/routing";
import { Brand } from "../brand/Brand";
import { Dialog } from "../ui/Dialog";
import { Icon, type IconName } from "../ui/Icon";

/** Props for {@link SiteHeader}. */
export interface SiteHeaderProps {
  /** The signed-in role, or null on the login page (no profile link). */
  role: Role | null;
}

const HELP_KEY = { student: "shell.helpStudent", staff: "shell.helpStaff", admin: "shell.helpAdmin" } as const;

const ICON_BUTTON =
  "inline-flex size-10 items-center justify-center rounded-md text-accent transition-colors duration-(--cp-motion-fast) hover:bg-surface-1";

function IconLink({ href, icon, label }: { href: string; icon: IconName; label: string }) {
  return (
    <Link href={href} aria-label={label} title={label} className={ICON_BUTTON}>
      <Icon name={icon} size={20} strokeWidth={1.8} />
    </Link>
  );
}

/**
 * The portal header: one slim white band with the plain "CampusPulse" wordmark at the start and two
 * icon buttons at the end: Help, and for staff and admins a link to Profile (students have Profile as
 * a tab). Language and Sign out live on the Profile page, and the login card has its own language
 * switch. No university logo or name appears here. The skip link is the first focusable element.
 */
export function SiteHeader({ role }: SiteHeaderProps) {
  const t = useT();
  const [help, setHelp] = useState(false);

  return (
    <header className="shrink-0">
      <a
        href="#content"
        className="sr-only z-50 rounded-md bg-surface-0 px-3 py-2 font-semibold text-accent focus:not-sr-only focus:absolute focus:start-2 focus:top-2"
      >
        {t("app.skipToContent")}
      </a>
      <div data-band className="border-b border-line bg-band text-on-band">
        <div className="flex items-center gap-2 px-3 py-1.5 sm:px-4">
          <Link href="/" aria-label={t("shell.home")} className="shrink-0 rounded-md">
            <Brand compact />
          </Link>
          <div className="ms-auto flex items-center gap-1">
            <button type="button" onClick={() => setHelp(true)} aria-label={t("shell.help")} title={t("shell.help")} className={ICON_BUTTON}>
              <Icon name="help" size={20} strokeWidth={1.8} />
            </button>
            {(role === "staff" || role === "admin") && <IconLink href="/profile" icon="user" label={t("nav.profile")} />}
          </div>
        </div>
      </div>
      <Dialog open={help} onClose={() => setHelp(false)} title={t("shell.helpTitle")}>
        <div className="flex flex-col gap-3">
          {role && <p>{t(HELP_KEY[role])}</p>}
          <p className="text-sm text-fg-2">{t("shell.helpNote")}</p>
        </div>
      </Dialog>
    </header>
  );
}
