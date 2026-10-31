"use client";

import { useT } from "@/i18n";
import { PageHeader } from "../shell/PageHeader";

/** Page title and subtitle of the login page (translated, so it lives in a client component). */
export function LoginHeading() {
  const t = useT();
  return (
    <PageHeader title={t("auth.title")} subtitle={`${t("shell.loginTitle")}. ${t("auth.subtitle")}`} />
  );
}
