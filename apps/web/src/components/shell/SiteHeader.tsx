"use client";

import Link from "next/link";
import { useState } from "react";
import { useSignOut } from "@/hooks/useSignIn";
import { useT } from "@/i18n";
import type { Role } from "@/lib/auth/routing";
import { Brand } from "../brand/Brand";
import { Dialog } from "../ui/Dialog";
import { Icon, type IconName } from "../ui/Icon";
import { LanguageSwitch } from "../ui/LanguageSwitch";

/** Props for {@link SiteHeader}. */
export interface SiteHeaderProps {
  /** The signed-in role, or null on the login page (no menu, no sign-out). */
  role: Role | null;
  /** The name shown as "Hello <name>" (the display name, or the alias while no display name exists). */
  name?: string | null;
}

const HELP_KEY = { student: "shell.helpStudent", staff: "shell.helpStaff", admin: "shell.helpAdmin" } as const;

function UtilityButton({ icon, label, onClick }: { icon: IconName; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex min-h-10 items-center gap-1.5 rounded-md px-2.5 text-sm font-medium text-accent transition-colors duration-(--cp-motion-fast) hover:bg-surface-1"
    >
      <Icon name={icon} size={18} strokeWidth={1.8} />
      <span className="max-sm:sr-only">{label}</span>
    </button>
  );
}

/**
 * The portal header: one white band with the plain "CampusPulse" wordmark and "Hello <name>" at the
 * start, and the utility links (Help, language switch, Sign out) at the end. No university logo or
 * name appears here. The skip link is the first focusable element on every page.
 */
export function SiteHeader({ role, name }: SiteHeaderProps) {
  const t = useT();
  const signOut = useSignOut();
  const [help, setHelp] = useState(false);

  return (
    <header>
      <a
        href="#content"
        className="sr-only z-50 rounded-md bg-surface-0 px-3 py-2 font-semibold text-accent focus:not-sr-only focus:absolute focus:start-2 focus:top-2"
      >
        {t("app.skipToContent")}
      </a>
      <div data-band className="border-b border-line bg-band text-on-band">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3">
          <div className="flex min-w-0 items-center gap-4">
            <Link href="/" aria-label={t("shell.home")} className="shrink-0 rounded-md">
              <Brand compact />
            </Link>
            {name && <p className="min-w-0 truncate text-sm font-medium">{t("shell.hello", { name })}</p>}
          </div>
          <div className="flex items-center gap-1">
            <UtilityButton icon="help" label={t("shell.help")} onClick={() => setHelp(true)} />
            <LanguageSwitch />
            {role && <UtilityButton icon="logout" label={t("auth.signOut")} onClick={() => void signOut()} />}
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
