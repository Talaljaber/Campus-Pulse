"use client";

import { translate } from "@/i18n";

/**
 * The slim disclosure strip under every page (root layout, so also the login page). The demo line
 * ("simulated portal, not the official university system, no real department is contacted") is always
 * shown in both English and Arabic, whatever the UI language, because it is a disclosure, not a
 * preference. It is one short band so the page keeps its height.
 */
export function SiteFooter() {
  return (
    <footer data-footer className="shrink-0 bg-footer text-on-footer">
      <div className="mx-auto flex flex-col items-center gap-0.5 px-3 py-1.5 text-center text-[10px] leading-snug font-semibold sm:flex-row sm:justify-center sm:gap-6 sm:text-xs">
        <p lang="en" dir="ltr">
          {translate("en", "shell.demoLine")}
        </p>
        <p lang="ar" dir="rtl">
          {translate("ar", "shell.demoLine")}
        </p>
      </div>
    </footer>
  );
}
