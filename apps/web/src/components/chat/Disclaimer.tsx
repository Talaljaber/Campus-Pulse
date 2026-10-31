"use client";

import { useT } from "@/i18n";

/** The footer line: an integration-ready prototype on synthetic data, not an official GJU service. */
export function Disclaimer() {
  const t = useT();
  return <p className="text-center text-sm text-fg-3">{t("disclaimer")}</p>;
}
