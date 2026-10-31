/** Small time helpers shared by the staff and pulse pages. */

/**
 * A timestamp in Amman time, in the page language (Latin digits in Arabic too, like the rest of the UI).
 * An unparseable value is returned as written, so a bad row never renders blank.
 */
export function formatDateTime(iso: string, lang: "en" | "ar"): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const locale = lang === "ar" ? "ar-JO-u-nu-latn" : "en-GB";
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Amman" }).format(date);
}

/** A span split into a whole number and a unit, so the UI picks the right translated unit. */
export function durationParts(ms: number): { unit: "minutes" | "hours" | "days"; n: number } {
  const abs = Math.abs(ms);
  if (abs < 3_600_000) return { unit: "minutes", n: Math.max(1, Math.round(abs / 60_000)) };
  if (abs < 86_400_000) return { unit: "hours", n: Math.round(abs / 3_600_000) };
  return { unit: "days", n: Math.round(abs / 86_400_000) };
}
