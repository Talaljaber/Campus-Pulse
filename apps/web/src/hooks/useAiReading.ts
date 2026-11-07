"use client";

import { useEffect, useState } from "react";
import { callAi } from "@/lib/ai/browser";

/** One read-only AI-service answer: loading, ready with data, or failed. */
export type Remote<T> = { state: "loading" } | { state: "ready"; data: T } | { state: "error" };

/**
 * Reads `GET /v1/<path>` once through the same-origin proxy (which adds the service token and the
 * user's JWT). Used by the admin Overview for the LLM spend and the service health.
 */
export function useAiReading<T>(path: string, timeoutMs = 15_000): Remote<T> {
  const [value, setValue] = useState<Remote<T>>({ state: "loading" });
  useEffect(() => {
    let live = true;
    void callAi<T>(path, { timeoutMs }).then((res) => {
      if (live) setValue(res.ok && res.data ? { state: "ready", data: res.data } : { state: "error" });
    });
    return () => {
      live = false;
    };
  }, [path, timeoutMs]);
  return value;
}
