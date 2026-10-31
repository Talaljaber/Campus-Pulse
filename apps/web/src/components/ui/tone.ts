/** Tones shared by Badge, Chip and Toast. Each non-neutral tone maps to a `--cp-<tone>` token. */
export type CategoryTone =
  | "cat-registration"
  | "cat-it"
  | "cat-finance"
  | "cat-transport"
  | "cat-facilities"
  | "cat-academic";
export type PriorityTone = "pri-low" | "pri-medium" | "pri-high";
export type SemanticTone = "neutral" | "ok" | "warn" | "danger" | "info";
export type Tone = SemanticTone | CategoryTone | PriorityTone;

/** CSS colour expression for a tone (a live token reference, so it follows the theme). */
export function toneColor(tone: Tone): string {
  return tone === "neutral" ? "var(--cp-text-3)" : `var(--cp-${tone})`;
}

/** Exact backend category label to its tone. */
export const CATEGORY_TONE: Record<string, CategoryTone> = {
  Registration: "cat-registration",
  "IT Support": "cat-it",
  Finance: "cat-finance",
  Transportation: "cat-transport",
  Facilities: "cat-facilities",
  "Academic Support": "cat-academic",
};

/** Exact backend priority label to its tone. */
export const PRIORITY_TONE: Record<string, PriorityTone> = {
  low: "pri-low",
  medium: "pri-medium",
  high: "pri-high",
};

/** Class string for a tinted surface keyed to `--tone` (set it via `style`). */
export function tintClass(pct: 16 | 28): string {
  return pct === 16
    ? "bg-[color-mix(in_srgb,var(--tone)_16%,var(--cp-surface-0))]"
    : "bg-[color-mix(in_srgb,var(--tone)_28%,var(--cp-surface-0))]";
}
