"use client";

import { LanguageSwitch } from "@/components/ui";
import { useT } from "@/i18n";

/** Placeholder landing page; the student chat replaces it in P5.8. */
export default function Home() {
  const t = useT();
  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-4 p-6">
      <div className="flex justify-end">
        <LanguageSwitch />
      </div>
      <h1 className="text-2xl font-bold">{t("app.name")}</h1>
      <p className="text-fg-2">{t("app.tagline")}</p>
      <p className="text-sm text-fg-3">{t("disclaimer")}</p>
    </main>
  );
}
