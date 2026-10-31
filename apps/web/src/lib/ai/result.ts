/**
 * Typed result of a call to the AI service, shared by the server client and the
 * browser helper. No secrets and no server-only imports live here.
 */

/** Error codes the API documents (docs/api/README.md > Errors) plus the ones the web layer adds. */
export type AiErrorCode =
  | "unauthenticated"
  | "forbidden"
  | "not_found"
  | "clarification_budget_exceeded"
  | "invalid_input"
  | "internal_error"
  | "not_implemented"
  | "artifact_unavailable"
  | "store_unavailable"
  // added by the web layer
  | "ai_waking"
  | "ai_not_configured"
  | "bad_gateway"
  | "network";

export interface AiOk<T> {
  ok: true;
  data: T;
}

export interface AiFail {
  ok: false;
  status: number;
  code: AiErrorCode;
  /** The API's `message`. Server prose: shown in logs and developer UI only, not to students. */
  error: string;
  details: unknown;
  /** True when the service is probably cold-starting (timeout, network error, or an empty 502/503/504 from Render). */
  waking: boolean;
}

export type AiResult<T> = AiOk<T> | AiFail;

const KNOWN_CODES: ReadonlySet<string> = new Set<AiErrorCode>([
  "unauthenticated",
  "forbidden",
  "not_found",
  "clarification_budget_exceeded",
  "invalid_input",
  "internal_error",
  "not_implemented",
  "artifact_unavailable",
  "store_unavailable",
  "ai_waking",
  "ai_not_configured",
  "bad_gateway",
  "network",
]);

/** Statuses Render's proxy returns while the service is starting. */
const WAKING_STATUSES: ReadonlySet<number> = new Set([502, 503, 504]);

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/** Parses the API error body `{"error": {code, message, details}}`, or returns null when the body is something else. */
export function parseErrorBody(body: unknown): { code: AiErrorCode; message: string; details: unknown } | null {
  if (!isRecord(body) || !isRecord(body.error)) return null;
  const { code, message, details } = body.error;
  if (typeof code !== "string" || typeof message !== "string") return null;
  return { code: KNOWN_CODES.has(code) ? (code as AiErrorCode) : "internal_error", message, details: details ?? null };
}

/**
 * Maps a non-2xx response to a typed failure. A 502/503/504 that does not carry the API's
 * own error body comes from Render's edge while the service boots, so it counts as `waking`.
 * A 503 with the API body (`artifact_unavailable`, `store_unavailable`) is a real error.
 */
export function failFromResponse(status: number, body: unknown): AiFail {
  const parsed = parseErrorBody(body);
  if (parsed) {
    // The proxy adds a top-level `waking` flag to the API's error shape.
    const flagged = isRecord(body) && body.waking === true;
    return {
      ok: false,
      status,
      code: parsed.code,
      error: parsed.message,
      details: parsed.details,
      waking: flagged || parsed.code === "ai_waking",
    };
  }
  const waking = WAKING_STATUSES.has(status);
  return {
    ok: false,
    status,
    code: waking ? "ai_waking" : "bad_gateway",
    error: waking ? "The AI service is starting." : `Unexpected response (${status}).`,
    details: null,
    waking,
  };
}

/** A failure for a request that never got a response (timeout, DNS, refused connection). */
export function failFromNetwork(timedOut: boolean): AiFail {
  return {
    ok: false,
    status: 503,
    code: timedOut ? "ai_waking" : "network",
    error: timedOut ? "The AI service did not answer in time." : "The AI service is unreachable.",
    details: null,
    waking: true,
  };
}
