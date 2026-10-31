import { describe, expect, it } from "vitest";
import {
  INITIAL_HEALTH,
  WAKING_PROBES_BEFORE_DOWN,
  nextHealth,
  outcomeOf,
  pollDelay,
  type HealthTrack,
} from "@/lib/ai/health";
import { failFromNetwork, failFromResponse } from "@/lib/ai/result";
import type { HealthResponse } from "@/lib/ai/types";

const health = (status: "ok" | "degraded"): HealthResponse => ({
  status,
  version: "0.1.0",
  artifact: "v1",
  sha: null,
  rss_mb: 1,
  encoder_loaded: true,
  sinks: [],
  llm_tiers: [],
  vector_store: null,
});

describe("outcomeOf", () => {
  it("classifies answers", () => {
    expect(outcomeOf({ ok: true, data: health("ok") })).toBe("ok");
    expect(outcomeOf({ ok: true, data: health("degraded") })).toBe("degraded");
  });
  it("treats timeouts, network errors and empty 502/503 as unreachable", () => {
    expect(outcomeOf(failFromNetwork(true))).toBe("unreachable");
    expect(outcomeOf(failFromNetwork(false))).toBe("unreachable");
    expect(outcomeOf(failFromResponse(502, null))).toBe("unreachable");
  });
  it("treats a real API error or a missing configuration as degraded", () => {
    expect(outcomeOf(failFromResponse(500, { error: { code: "internal_error", message: "x", details: null } }))).toBe("degraded");
    expect(outcomeOf(failFromResponse(404, "nope"))).toBe("degraded");
  });
});

describe("nextHealth", () => {
  it("goes waking on the first miss and down after a minute of misses", () => {
    let t: HealthTrack = INITIAL_HEALTH;
    t = nextHealth(t, "unreachable");
    expect(t.state).toBe("waking");
    for (let i = 1; i < WAKING_PROBES_BEFORE_DOWN - 1; i++) t = nextHealth(t, "unreachable");
    expect(t.state).toBe("waking");
    t = nextHealth(t, "unreachable");
    expect(t.state).toBe("down");
  });
  it("recovers to ok at once", () => {
    const waking = nextHealth(INITIAL_HEALTH, "unreachable");
    expect(nextHealth(waking, "ok")).toEqual(INITIAL_HEALTH);
  });
  it("a degraded service is down immediately", () => {
    expect(nextHealth(INITIAL_HEALTH, "degraded").state).toBe("down");
  });
});

describe("pollDelay", () => {
  it("polls every 30 s when ok and every 5 s otherwise", () => {
    expect(pollDelay("ok")).toBe(30_000);
    expect(pollDelay("waking")).toBe(5_000);
    expect(pollDelay("down")).toBe(5_000);
  });
});
