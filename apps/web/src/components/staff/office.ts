"use client";

import { useT, type DictKey } from "@/i18n";

const OFFICES = new Set(["registrar", "it", "finance", "transport", "facilities", "academic"]);

/** Returns a function from an office code (D-005) to its translated name; an unknown code is shown as is. */
export function useOfficeLabel(): (code: string) => string {
  const t = useT();
  return (code) => (OFFICES.has(code) ? t(`staff.offices.${code}` as DictKey) : code);
}
