/** The red-team form: styles the API accepts, limits and how a form becomes a request. Pure. */
import type { RedTeamRunRequest } from "@/lib/ai/types";

/** The red-team styles the API accepts (`RedTeamRunRequest.styles`), in the order the form lists them. */
export const RED_TEAM_STYLES = [
  "fake_urgency",
  "calm_emergency",
  "typos",
  "arabizi",
  "mixed_language",
  "two_issues",
  "very_long",
  "injection",
  "off_topic",
  "distress_adjacent",
] as const;
export type RedTeamStyle = (typeof RED_TEAM_STYLES)[number];

/** The service refuses more items than this (`REDTEAM_MAX_N`). */
export const RED_TEAM_MAX_N = 200;
export const RED_TEAM_DEFAULT_N = 20;
export const RED_TEAM_DEFAULT_SEED = 42;

/** What the red-team form holds. */
export interface RedTeamForm {
  styles: ReadonlySet<string>;
  n: number;
  seed: number;
}

/** True when `n` is a whole number the service will accept. */
export function validRedTeamN(n: number): boolean {
  return Number.isInteger(n) && n >= 1 && n <= RED_TEAM_MAX_N;
}

/** The request body for a form. Choosing every style is sent as `null`, which the service reads as "all". */
export function redTeamRequest(form: RedTeamForm): RedTeamRunRequest {
  const all = RED_TEAM_STYLES.every((s) => form.styles.has(s));
  return {
    n: form.n,
    styles: all ? null : RED_TEAM_STYLES.filter((s) => form.styles.has(s)),
    seed: form.seed,
  };
}
