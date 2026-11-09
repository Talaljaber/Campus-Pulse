import "server-only";
import { failFromNetwork, failFromResponse, type AiFail, type AiResult } from "./result";

/** A path below `/v1`, already checked against the allow-list (no leading slash, may carry a query string). */
export type AiPath = string;

export interface AiFetchInit {
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  /** JSON-serialisable body, or `FormData` for the batch upload. */
  body?: unknown;
  /** The signed-in user's Supabase access token, forwarded as `X-CP-User-JWT`. `null` for public calls. */
  userJwt: string | null;
  /** Milliseconds before giving up. Default 20 000 (a Render cold start looks like a timeout). */
  timeoutMs?: number;
}

const DEFAULT_TIMEOUT_MS = 20_000;

function notConfigured(): AiFail {
  return {
    ok: false,
    status: 503,
    code: "ai_not_configured",
    error: "AI_SERVICE_URL and AI_SERVICE_TOKEN are not set.",
    details: null,
    waking: false,
  };
}

/** FormData from any realm (the route handler's request parser and the global one can be different classes). */
const isFormData = (v: unknown): v is FormData => v instanceof FormData || Object.prototype.toString.call(v) === '[object FormData]';

/**
 * Calls the FastAPI service. This module is the only place that reads `AI_SERVICE_URL`
 * and `AI_SERVICE_TOKEN` (LD-25); `server-only` makes a client import a build error.
 *
 * Sends `Authorization: Bearer <AI_SERVICE_TOKEN>` and, when given, the user's Supabase
 * JWT as `X-CP-User-JWT`. The service reads role, office and alias from the verified JWT,
 * never from a header the browser can set. Never throws: every failure is an `AiResult`.
 */
export async function aiFetch<T>(path: AiPath, init: AiFetchInit): Promise<AiResult<T>> {
  const base = process.env.AI_SERVICE_URL;
  const token = process.env.AI_SERVICE_TOKEN;
  if (!base || !token) return notConfigured();

  const headers: Record<string, string> = { Authorization: `Bearer ${token}`, Accept: "application/json, text/csv" };
  if (init.userJwt) headers["X-CP-User-JWT"] = init.userJwt;

  let body: BodyInit | undefined;
  if (isFormData(init.body)) {
    body = init.body; // fetch sets the multipart boundary itself
  } else if (init.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(init.body);
  }

  let res: Response;
  try {
    res = await fetch(`${base.replace(/\/+$/, "")}/v1/${path}`, {
      method: init.method,
      headers,
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(init.timeoutMs ?? DEFAULT_TIMEOUT_MS),
    });
  } catch (err) {
    const timedOut = err instanceof DOMException && (err.name === "TimeoutError" || err.name === "AbortError");
    return failFromNetwork(timedOut);
  }

  const isJson = (res.headers.get("content-type") ?? "").includes("json");
  let parsed: unknown = null;
  let unreadable = false;
  try {
    parsed = isJson ? await res.json() : await res.text();
  } catch {
    parsed = null;
    unreadable = true;
  }
  if (!res.ok) return failFromResponse(res.status, parsed);
  // A 2xx whose body was cut off (timeout while reading) or is not JSON is not a success with data.
  if (unreadable) return failFromNetwork(true);
  return { ok: true, data: parsed as T };
}
