"use client";

import { useT } from "@/i18n";

/** Page title and subtitle of the login page (translated, so it lives in a client component). */
export function LoginHeading() {
  const t = useT();
  return (
    <header className="flex flex-col gap-1">
      <h1 className="text-2xl font-bold">{t("auth.title")}</h1>
      <p className="text-fg-2">{t("auth.subtitle")}</p>
    </header>
  );
}
