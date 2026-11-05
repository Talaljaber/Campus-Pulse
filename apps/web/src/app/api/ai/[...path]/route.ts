import { NextResponse, type NextRequest } from "next/server";
import { matchAllowed } from "@/lib/ai/allowlist";
import { aiFetch } from "@/lib/ai/client";
import type { AiFail } from "@/lib/ai/result";
import { createServerSupabase } from "@/lib/supabase/server";

// Always dynamic: it forwards per-user calls and must never be cached.
export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ path: string[] }> };

/** The error shape the browser helper parses: the API's own body, plus `waking`. */
function errorResponse(f: AiFail): NextResponse {
  return NextResponse.json(
    { error: { code: f.code, message: f.error, details: f.details }, waking: f.waking },
    { status: f.status, headers: { "Cache-Control": "no-store" } },
  );
}

const fail = (status: number, code: AiFail["code"], error: string): NextResponse =>
  errorResponse({ ok: false, status, code, error, details: null, waking: false });

/** The profile alias for a student: trusted server-side, never taken from the browser. */
async function aliasOf(userId: string, sb: Awaited<ReturnType<typeof createServerSupabase>>): Promise<string | null> {
  const { data } = await sb.from("profiles").select("alias").eq("id", userId).maybeSingle();
  return data?.alias ?? null;
}

async function handle(req: NextRequest, ctx: Ctx): Promise<NextResponse> {
  const { path: segments } = await ctx.params;
  const allowed = matchAllowed(req.method, segments);
  if (!allowed) return fail(404, "not_found", "Not found.");

  // The session is verified with Supabase (getUser), not just decoded from the cookie.
  let userJwt: string | null = null;
  let alias: string | null = null;
  if (!allowed.public) {
    const sb = await createServerSupabase();
    const { data: userData } = await sb.auth.getUser();
    const { data: sessionData } = await sb.auth.getSession();
    if (!userData.user || !sessionData.session) return fail(401, "unauthenticated", "Sign in first.");
    userJwt = sessionData.session.access_token;
    if (allowed.path === "triage") alias = await aliasOf(userData.user.id, sb);
  }

  // Only the verified session token is forwarded. Any Authorization or X-CP-* header the
  // browser sent is dropped here because aiFetch builds its headers from scratch.
  let body: unknown;
  if (req.method !== "GET" && req.method !== "DELETE") {
    const type = req.headers.get("content-type") ?? "";
    try {
      body = type.includes("multipart/form-data") ? await req.formData() : await req.json();
    } catch {
      return fail(422, "invalid_input", "The request body is not valid.");
    }
    if (alias !== null && typeof body === "object" && body !== null && !(body instanceof FormData)) {
      body = { ...(body as Record<string, unknown>), student_alias: alias };
    }
  }

  const search = req.nextUrl.search;
  const result = await aiFetch<unknown>(`${allowed.path}${search}`, {
    method: req.method as "GET" | "POST" | "PUT" | "DELETE",
    body,
    userJwt,
    timeoutMs: allowed.public ? 3_000 : undefined,
  });
  if (!result.ok) return errorResponse(result);
  const headers = { "Cache-Control": "no-store" };
  return typeof result.data === "string"
    ? new NextResponse(result.data, { headers: { ...headers, "Content-Type": "text/csv; charset=utf-8" } })
    : NextResponse.json(result.data, { headers });
}

export const GET = handle;
export const POST = handle;
export const PUT = handle;
export const DELETE = handle;
