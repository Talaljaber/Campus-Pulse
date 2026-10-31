"use client";

import Link from "next/link";
import { useState } from "react";
import { useSignOut } from "@/hooks/useSignIn";
import { useT } from "@/i18n";
import type { Role } from "@/lib/auth/routing";
import { Brand } from "../brand/Brand";
import { cn } from "../ui/cn";
import { Dialog } from "../ui/Dialog";
import { Icon, type IconName } from "../ui/Icon";
import { LanguageSwitch } from "../ui/LanguageSwitch";
import { RoleNav, type NavPage } from "./RoleNav";

/** Props for {@link SiteHeader}. */
export interface SiteHeaderProps {
  /** The signed-in role, or null on the login page (no menu, no sign-out). */
  role: Role | null;
  /** The page being shown, for the nav row. */
  current?: NavPage;
  /** The signed-in user's alias, shown as "Hello <alias>". */
  alias?: string | null;
}

const HELP_KEY = { student: "shell.helpStudent", staff: "shell.helpStaff", admin: "shell.helpAdmin" } as const;

function UtilityButton({ icon, label, onClick }: { icon: IconName; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex min-h-10 items-center gap-1.5 rounded-md px-2.5 text-sm font-medium text-on-band transition-colors duration-(--cp-motion-fast) hover:bg-white/15"
    >
      <Icon name={icon} size={18} strokeWidth={1.8} />
      <span className="max-sm:sr-only">{label}</span>
    </button>
  );
}

/**
 * The portal header: a blue top band holding the logo card and "Hello <alias>", a darker icon bar
 * with the utility links (Help, Sign out), and a white nav row with the role's uppercase links and
 * the language switch. The logo card straddles the two bands like the university's own site.
 * White text on the bands is contrast-tested (tokens test); the focus ring turns white there.
 */
export function SiteHeader({ role, current, alias }: SiteHeaderProps) {
  const t = useT();
  const signOut = useSignOut();
  const [help, setHelp] = useState(false);

  return (
    <header>
      <a
        href="#main"
        className="sr-only z-50 rounded-md bg-surface-0 px-3 py-2 font-semibold text-accent focus:not-sr-only focus:absolute focus:start-2 focus:top-2"
      >
        {t("app.skipToContent")}
      </a>
      <div data-band className="bg-band text-on-band">
        <div className="relative mx-auto flex h-12 max-w-7xl items-center justify-end px-4">
          <Link
            href="/"
            aria-label={t("shell.home")}
            className="absolute start-4 top-2 z-10 rounded-xl border border-line bg-surface-0 px-3.5 py-2.5 shadow-card"
          >
            <Brand />
          </Link>
          {alias && <p className="min-w-0 truncate text-sm font-medium">{t("shell.hello", { name: alias })}</p>}
        </div>
      </div>
      <div data-band className="bg-band-2 text-on-band">
        <div className="mx-auto flex h-11 max-w-7xl items-center justify-end gap-1 px-4">
          <UtilityButton icon="help" label={t("shell.help")} onClick={() => setHelp(true)} />
          {role && <UtilityButton icon="logout" label={t("auth.signOut")} onClick={() => void signOut()} />}
        </div>
      </div>
      <div className="border-b border-line bg-surface-0 shadow-1">
        <div className={cn("mx-auto flex max-w-7xl flex-wrap items-center gap-x-4 px-4", role ? "justify-between" : "justify-end")}>
          {role && <RoleNav role={role} current={current ?? "request"} />}
          <LanguageSwitch className="my-1.5" />
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
