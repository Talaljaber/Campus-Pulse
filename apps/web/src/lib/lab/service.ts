import { callAi } from "@/lib/ai/browser";
import type { AiFail, AiResult } from "@/lib/ai/result";
import type { MetricsResponse, RedTeamRunRequest, Scorecard } from "@/lib/ai/types";

/** Why a lab call failed, as the UI says it (dictionary key `lab.error.<kind>`). */
export type LabErrorKind = "generic" | "waking" | "session" | "forbidden" | "invalid" | "unavailable";

/** `GET /v1/metrics` (admin): offline report plus live router, memory and red-team numbers. */
export function fetchMetrics(): Promise<AiResult<MetricsResponse>> {
  return callAi<MetricsResponse>("metrics");
}

/** `POST /v1/redteam/run` (admin): runs the generated attacks through the real pipeline and scores them. */
export function runRedTeam(req: RedTeamRunRequest): Promise<AiResult<Scorecard>> {
  return callAi<Scorecard>("redteam/run", { method: "POST", body: req });
}

/**
 * Maps a failed call to a dictionary entry: the API's prose is English and technical, so the
 * admin sees our sentence in the page language instead.
 */
export function labErrorKind(fail: AiFail): LabErrorKind {
  if (fail.status === 401 || fail.code === "unauthenticated") return "session";
  if (fail.status === 403 || fail.code === "forbidden") return "forbidden";
  if (fail.status === 422 || fail.code === "invalid_input") return "invalid";
  if (fail.code === "artifact_unavailable" || fail.code === "store_unavailable") return "unavailable";
  if (fail.waking) return "waking";
  return "generic";
}
