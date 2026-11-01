"use client";

import { useT, type DictKey } from "@/i18n";

/** The D-005 office codes, in the order the pickers list them. */
export const OFFICE_CODES = ["registrar", "it", "finance", "transport", "facilities", "academic"] as const;
const OFFICES = new Set<string>(OFFICE_CODES);

/** The office that owns a category (one office per category, D-005), or null for an unknown one. */
export function officeOfCategory(category: string): string | null {
  const map: Record<string, string> = {
    Registration: "registrar",
    "IT Support": "it",
    Finance: "finance",
    Transportation: "transport",
    Facilities: "facilities",
    "Academic Support": "academic",
  };
  return map[category] ?? null;
}

/** Returns a function from an office code (D-005) to its translated name; an unknown code is shown as is. */
export function useOfficeLabel(): (code: string) => string {
  const t = useT();
  return (code) => (OFFICES.has(code) ? t(`staff.offices.${code}` as DictKey) : code);
}
