/** Small time helpers shared by the staff and pulse pages. */

/** A span split into a whole number and a unit, so the UI picks the right translated unit. */
export function durationParts(ms: number): { unit: "minutes" | "hours" | "days"; n: number } {
  const abs = Math.abs(ms);
  if (abs < 3_600_000) return { unit: "minutes", n: Math.max(1, Math.round(abs / 60_000)) };
  if (abs < 86_400_000) return { unit: "hours", n: Math.round(abs / 3_600_000) };
  return { unit: "days", n: Math.round(abs / 86_400_000) };
}
