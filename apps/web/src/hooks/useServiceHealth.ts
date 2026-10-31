"use client";

import { useEffect, useState } from "react";
import { callAi } from "@/lib/ai/browser";
import {
  INITIAL_HEALTH,
  PROBE_TIMEOUT_MS,
  nextHealth,
  outcomeOf,
  pollDelay,
  type HealthTrack,
  type ServiceState,
} from "@/lib/ai/health";
import type { HealthResponse } from "@/lib/ai/types";

/**
 * Polls `/api/ai/health` (30 s while healthy, 5 s while waking; a probe that takes more
 * than 3 s counts as "waking") and returns the banner state. Nothing is shown before the
 * first answer, so a fast service never flashes a banner.
 */
export function useServiceHealth(): ServiceState {
  const [track, setTrack] = useState<HealthTrack>(INITIAL_HEALTH);

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let current = INITIAL_HEALTH;
    const controller = new AbortController();

    const probe = async () => {
      const res = await callAi<HealthResponse>("health", { timeoutMs: PROBE_TIMEOUT_MS, signal: controller.signal });
      if (stopped) return;
      current = nextHealth(current, outcomeOf(res));
      setTrack(current);
      timer = setTimeout(probe, pollDelay(current.state));
    };
    void probe();

    return () => {
      stopped = true;
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, []);

  return track.state;
}
