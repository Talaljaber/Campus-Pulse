import { NextResponse, type NextRequest } from "next/server";
import { decideRoute } from "@/lib/auth/routing";
import { carryCookies, readSession } from "@/lib/auth/session";

/**
 * Next 16's `proxy` (the former `middleware`). Refreshes the Supabase session and sends
 * each role where it belongs: student `/`, staff `/staff`, admin `/lab`; `/staff`,
 * `/pulse` and `/outbox` need staff or admin, `/lab` needs admin. The decision itself
 * is `decideRoute`; this file only wires it to the request.
 */
export async function proxy(request: NextRequest): Promise<NextResponse> {
  const { role, response } = await readSession(request);
  const decision = decideRoute(request.nextUrl.pathname, role);
  if (decision.action === "next") return response;
  return carryCookies(response, NextResponse.redirect(new URL(decision.to, request.url)));
}

export const config = {
  // API routes authenticate themselves; static assets need no session.
  matcher: ["/((?!api/|_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)"],
};
