/**
 * The only `/v1` paths the browser may reach through `/api/ai/...`. Anything else is a
 * 404, so the proxy can never become a general relay to the AI service. Not listed on
 * purpose: `integrations/linear/webhook` (authenticated by its own HMAC, never from a browser).
 */

export type AiMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

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
  // P9.7: the requester's answer on their own ticket.
  rule("POST", "tickets/{id}/student-action"),
  rule("GET", "reviews"),
  rule("POST", "reviews/{id}/forward"),
  rule("GET", "incidents"),
  rule("POST", "incidents/{id}/resolve"),
  rule("GET", "insights/recurring"),
  rule("GET", "health", { public: true }),
  // P10.17: the admin Overview's LLM spend. The model lab routes (metrics, batch, red team) are no
  // longer reachable from the browser.
  rule("GET", "admin/usage"),
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
  rule("GET", "profile/email"),
  rule("PUT", "profile/email"),
  rule("DELETE", "profile/email"),
  // P9.10 ticket files: a multipart upload (forwarded as is by the proxy) and the 60-second signed link.
  rule("POST", "tickets/{id}/files"),
  rule("GET", "files/{id}/link"),
  // P10.19 admin knowledge base: a multipart upload (forwarded as is), the list, and delete.
  rule("POST", "admin/knowledge"),
  rule("GET", "admin/knowledge"),
  rule("DELETE", "admin/knowledge/{id}"),
  // Suggested announcement drafts from incidents: list, edit, publish, dismiss.
  rule("GET", "announcement-drafts"),
  rule("PATCH", "announcement-drafts/{id}"),
  rule("POST", "announcement-drafts/{id}/publish"),
  rule("POST", "announcement-drafts/{id}/dismiss"),
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
