import { failFromNetwork, failFromResponse, type AiResult } from "./result";

export interface CallAiInit {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  /** JSON-serialisable body, or `FormData` (the browser then sets the multipart boundary itself). */
  body?: unknown;
  /** Abort after this many milliseconds. Default: none (the server proxy already times out at 20 s). */
  timeoutMs?: number;
  signal?: AbortSignal;
}

/**
 * Calls the AI service through the same-origin proxy `/api/ai/...` and maps the answer to
 * a typed result. It holds no secret: the proxy adds the service token and the verified
 * user JWT. Never throws.
 */
export async function callAi<T>(path: string, init: CallAiInit = {}): Promise<AiResult<T>> {
  const signals: AbortSignal[] = [];
  if (init.signal) signals.push(init.signal);
  if (init.timeoutMs) signals.push(AbortSignal.timeout(init.timeoutMs));
  const signal = signals.length > 1 ? AbortSignal.any(signals) : signals[0];

  let res: Response;
  try {
    res = await fetch(`/api/ai/${path}`, {
      method: init.method ?? "GET",
      headers: init.body === undefined || init.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
      body: init.body === undefined ? undefined : init.body instanceof FormData ? init.body : JSON.stringify(init.body),
      cache: "no-store",
      signal,
    });
  } catch (err) {
    const timedOut = err instanceof DOMException && (err.name === "TimeoutError" || err.name === "AbortError");
    return failFromNetwork(timedOut);
  }
  let parsed: unknown = null;
  let unreadable = false;
  try {
    parsed = (res.headers.get("content-type") ?? "").includes("json") ? await res.json() : await res.text();
  } catch {
    parsed = null;
    unreadable = true;
  }
  if (!res.ok) return failFromResponse(res.status, parsed);
  // A 2xx whose body was cut off (timeout while reading) or is not JSON is not a success with data.
  if (unreadable) return failFromNetwork(true);
  return { ok: true, data: parsed as T };
}
