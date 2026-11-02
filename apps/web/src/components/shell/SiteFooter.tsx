"use client";

import { translate, useT } from "@/i18n";

/**
 * The dark footer, on every page (root layout, so also the login page). The demo line ("simulated
 * portal, not the official university system, no real department is contacted") is always shown in
 * both English and Arabic, whatever the UI language, because it is a disclosure, not a preference.
 */
export function SiteFooter() {
  const t = useT();
  return (
    <footer data-footer className="bg-footer text-on-footer">
      <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-6 text-sm sm:flex-row sm:items-start sm:justify-between">
        <div className="flex flex-col gap-1.5">
          <p lang="en" dir="ltr" className="font-semibold">
            {translate("en", "shell.demoLine")}
          </p>
          <p lang="ar" dir="rtl" className="font-semibold">
            {translate("ar", "shell.demoLine")}
          </p>
        </div>
        <div className="flex flex-col gap-1.5 sm:text-end">
          <p>{t("shell.footerFictional")}</p>
          <p>{t("shell.footerBuilt")}</p>
        </div>
      </div>
    </footer>
  );
}
