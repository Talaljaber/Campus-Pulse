"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { MetricsResponse, RedTeamRunRequest, Scorecard } from "@/lib/ai/types";
import { fetchMetrics, labErrorKind, runRedTeam, type LabErrorKind } from "@/lib/lab/service";
import type { LoadState } from "./useTicketQueue";

/**
 * `GET /v1/metrics` once, with a retry. `refresh()` re-reads quietly (no skeleton) and keeps what is
 * on screen when the re-read fails, so a refresh after a red-team run never blanks the page.
 */
export function useLabMetrics() {
  const [data, setData] = useState<MetricsResponse | null>(null);
  const [load, setLoad] = useState<LoadState>("loading");
  const [error, setError] = useState<LabErrorKind | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let live = true;
    void fetchMetrics().then((res) => {
      if (!live) return;
      if (res.ok) {
        setData(res.data);
        setError(null);
        setLoad("ready");
      } else {
        setError(labErrorKind(res));
        setLoad((cur) => (cur === "ready" ? "ready" : "error"));
      }
    });
    return () => {
      live = false;
    };
  }, [nonce]);

  const reload = useCallback(() => {
    setLoad("loading");
    setNonce((n) => n + 1);
  }, []);
  const refresh = useCallback(() => setNonce((n) => n + 1), []);

  return { data, load, error, reload, refresh };
}

export type RedTeamOutcome = { ok: true; scorecard: Scorecard } | { ok: false; kind: LabErrorKind };

/** Starts red-team runs and remembers the scorecards of this session. One run at a time. */
export function useRedTeam() {
  const [running, setRunning] = useState(false);
  const [runs, setRuns] = useState<Scorecard[]>([]);
  const busy = useRef(false);

  const run = useCallback(async (req: RedTeamRunRequest): Promise<RedTeamOutcome> => {
    if (busy.current) return { ok: false, kind: "generic" };
    busy.current = true;
    setRunning(true);
    try {
      const res = await runRedTeam(req);
      if (!res.ok) return { ok: false, kind: labErrorKind(res) };
      setRuns((cur) => [res.data, ...cur.filter((s) => s.run_id !== res.data.run_id)]);
      return { ok: true, scorecard: res.data };
    } finally {
      busy.current = false;
      setRunning(false);
    }
  }, []);

  return { running, runs, run };
}
