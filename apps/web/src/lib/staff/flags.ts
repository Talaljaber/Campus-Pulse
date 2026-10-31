/**
 * The "flags" feed on the staff page: requests whose prediction carried a manipulation or
 * anti-gaming flag. It reads `predictions.flags` rather than the `events` audit log
 * because those flag names are part of the documented contract (docs/api/README.md >
 * Flags), whereas the audit action names are not.
 */
import { en } from "@/i18n/en";
import type { TriageFlag } from "@/lib/ai/types";
import type { PredictionRow } from "@/lib/repos/predictions";
import type { RequestRow } from "@/lib/repos/requests";

/** Keeps only the flag names the dictionary can print, as `TriageFlag`s (an unknown future flag is dropped, not shown raw). */
export function knownFlags(flags: readonly string[]): TriageFlag[] {
  return flags.filter((f): f is TriageFlag => f in en.flags);
}

/** Flags the panel watches. `priority_gaming_suspected` is only shown to admin. */
export const WATCHED_FLAGS = ["injection_attempt", "urgency_unsupported", "priority_gaming_suspected"] as const;
export type WatchedFlag = (typeof WATCHED_FLAGS)[number];

export interface FlagEvent {
  /** The prediction id (React key). */
  id: string;
  at: string;
  /** The watched flags this prediction carried, in watch order. */
  flags: WatchedFlag[];
  /** The request text when the caller may read it. */
  text: string | null;
}

/** Flag events newest first. Predictions with no watched flag are dropped. */
export function buildFlagEvents(predictions: readonly PredictionRow[], requests: readonly RequestRow[]): FlagEvent[] {
  const rById = new Map(requests.map((r) => [r.id, r]));
  return predictions
    .flatMap((p): FlagEvent[] => {
      const flags = WATCHED_FLAGS.filter((w) => p.flags.includes(w));
      if (flags.length === 0) return [];
      return [{ id: p.id, at: p.created_at, flags, text: rById.get(p.request_id)?.raw_text ?? null }];
    })
    .sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime());
}
