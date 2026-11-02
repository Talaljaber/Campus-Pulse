/**
 * The only `/v1` paths the browser may reach through `/api/ai/...`. Anything else is a
 * 404, so the proxy can never become a general relay to the AI service. Not listed on
 * purpose: `integrations/linear/webhook` (authenticated by its own HMAC, never from a browser).
 */

export type AiMethod = "GET" | "POST";

/** One id segment (UUIDs and slugs). No dots, slashes or percent signs, so no traversal. */
const ID = "[A-Za-z0-9_-]{1,64}";

interface Rule {
  method: AiMethod;
  pattern: RegExp;
  /** Reachable without a signed-in user. Only the health probe. */
  public?: true;
}

const rule = (method: AiMethod, path: string, extra: { public?: true } = {}): Rule => ({
  method,
  pattern: new RegExp(`^${path.replace("{id}", ID)}$`),
  ...extra,
});

export const AI_ALLOWLIST: readonly Rule[] = [
  rule("POST", "triage"),
  rule("POST", "triage/{id}/clarify"),
  rule("GET", "explain/{id}/counterfactual"),
  rule("POST", "feedback"),
  rule("POST", "tickets/{id}/status"),
  rule("POST", "tickets/{id}/forward"),
  // P9.6: ticket thread and priority (staff workspace).
  rule("POST", "tickets/{id}/comments"),
  rule("POST", "tickets/{id}/priority"),
  rule("GET", "reviews"),
  rule("POST", "reviews/{id}/forward"),
  rule("GET", "incidents"),
  rule("POST", "incidents/{id}/resolve"),
  rule("GET", "insights/recurring"),
  rule("POST", "redteam/run"),
  rule("GET", "metrics"),
  rule("POST", "batch"),
  rule("GET", "health", { public: true }),
  // Optional extras (B-list); a deployment without them answers 501 not_implemented.
  rule("POST", "admin/simulate"),
  rule("POST", "admin/reindex"),
  // P9.5 announcements (append new P9 rules below)
  rule("POST", "announcements"),
  rule("POST", "announcements/{id}/archive"),
  // P9.9 chat agent
  rule("POST", "chat/turn"),
  rule("POST", "chat/preview"),
  rule("POST", "chat/confirm"),
];

/** A path that passed the allow-list. */
export interface AllowedPath {
  /** Path below `/v1`, without a leading slash. */
  path: string;
  public: boolean;
}

/** Returns the matching entry, or null (the proxy answers 404). `segments` come straight from the catch-all route. */
export function matchAllowed(method: string, segments: readonly string[]): AllowedPath | null {
  if (segments.some((s) => s.includes("/"))) return null;
  const path = segments.join("/");
  const hit = AI_ALLOWLIST.find((r) => r.method === method.toUpperCase() && r.pattern.test(path));
  return hit ? { path, public: hit.public === true } : null;
}
