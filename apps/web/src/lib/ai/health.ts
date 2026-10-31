import type { HealthResponse } from "./types";
import type { AiResult } from "./result";

/** What the banner shows. `ok` renders nothing. */
export type ServiceState = "ok" | "waking" | "down";

export interface HealthTrack {
  state: ServiceState;
  /** Consecutive probes that got no answer. */
  failures: number;
}

export type ProbeOutcome = "ok" | "degraded" | "unreachable";

/** Render's free tier can take about a minute to boot: 12 probes at 5 s before we call it down. */
export const WAKING_PROBES_BEFORE_DOWN = 12;
export const POLL_OK_MS = 30_000;
export const POLL_RETRY_MS = 5_000;
/** A probe that has not answered in 3 s counts as "waking" (P5.7). */
export const PROBE_TIMEOUT_MS = 3_000;

export const INITIAL_HEALTH: HealthTrack = { state: "ok", failures: 0 };

/** Classifies one `/api/ai/health` call. */
export function outcomeOf(res: AiResult<HealthResponse>): ProbeOutcome {
  if (res.ok) return res.data.status === "ok" ? "ok" : "degraded";
  return res.waking ? "unreachable" : "degraded";
}

/**
 * Next banner state. A healthy answer clears everything. A service that answers but is
 * degraded (or misconfigured) is `down` at once. No answer is `waking` for the first
 * minute, then `down`.
 */
export function nextHealth(prev: HealthTrack, outcome: ProbeOutcome): HealthTrack {
  if (outcome === "ok") return INITIAL_HEALTH;
  if (outcome === "degraded") return { state: "down", failures: 0 };
  const failures = prev.failures + 1;
  return { state: failures >= WAKING_PROBES_BEFORE_DOWN ? "down" : "waking", failures };
}

/** Poll slowly while healthy, quickly while recovering. */
export function pollDelay(state: ServiceState): number {
  return state === "ok" ? POLL_OK_MS : POLL_RETRY_MS;
}
