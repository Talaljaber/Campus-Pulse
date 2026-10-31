// A tiny stand-in for Supabase, for Playwright only. It answers just what the chat flow
// calls (password sign-in, /auth/v1/user, profiles, buildings, notifications) so the e2e
// can run the real Next.js code paths without the live project or its password.
// It is a test double: it accepts one fixed password from E2E_PASSWORD and runs on localhost.
//
//   node e2e/support/fake-supabase.mjs        (PORT default 54399)

import { createHmac } from "node:crypto";
import { createServer } from "node:http";

const PORT = Number(process.env.FAKE_SUPABASE_PORT ?? 54399);
const PASSWORD = process.env.E2E_PASSWORD ?? "e2e-password";
const JWT_SECRET = "fake-supabase-e2e-secret-not-used-anywhere-else";

const USERS = {
  "talal@demo.local": { id: "00000000-0000-4000-8000-000000000001", role: "student", office: null, alias: "talal" },
  "it@demo.local": { id: "00000000-0000-4000-8000-000000000002", role: "staff", office: "it", alias: "staff-it" },
  "admin@demo.local": { id: "00000000-0000-4000-8000-000000000003", role: "admin", office: null, alias: "admin" },
};
const byId = (id) => Object.entries(USERS).find(([, u]) => u.id === id);

const BUILDINGS = [
  { id: "M", code: "M", name_en: "Technology Centre", name_ar: "مركز التقنية", map_x: 110, map_y: 250, created_at: "2026-01-01T00:00:00Z" },
  { id: "A", code: "A", name_en: "Administration", name_ar: "الإدارة", map_x: 140, map_y: 100, created_at: "2026-01-01T00:00:00Z" },
];

const b64 = (o) => Buffer.from(JSON.stringify(o)).toString("base64url");
function sign(payload) {
  const head = b64({ alg: "HS256", typ: "JWT" });
  const body = b64(payload);
  const sig = createHmac("sha256", JWT_SECRET).update(`${head}.${body}`).digest("base64url");
  return `${head}.${body}.${sig}`;
}
function verify(token) {
  const [h, b, s] = (token ?? "").split(".");
  if (!h || !b || !s) return null;
  const expected = createHmac("sha256", JWT_SECRET).update(`${h}.${b}`).digest("base64url");
  if (expected !== s) return null;
  const payload = JSON.parse(Buffer.from(b, "base64url").toString("utf8"));
  return payload.exp * 1000 > Date.now() ? payload : null;
}
const userObject = (email, u) => ({
  id: u.id,
  aud: "authenticated",
  role: "authenticated",
  email,
  app_metadata: {},
  user_metadata: {},
  created_at: "2026-01-01T00:00:00Z",
});

function send(res, status, body, extra = {}) {
  res.writeHead(status, {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Allow-Methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
    ...extra,
  });
  res.end(body === undefined ? "" : JSON.stringify(body));
}
const readBody = (req) =>
  new Promise((resolve) => {
    let data = "";
    req.on("data", (c) => (data += c));
    req.on("end", () => resolve(data ? JSON.parse(data) : {}));
  });

const server = createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", `http://localhost:${PORT}`);
  if (req.method === "OPTIONS") return send(res, 204);
  if (url.pathname === "/health") return send(res, 200, { ok: true });

  if (url.pathname === "/auth/v1/token" && req.method === "POST") {
    const { email, password } = await readBody(req);
    const user = USERS[String(email ?? "").toLowerCase()];
    if (!user || password !== PASSWORD) {
      return send(res, 400, { code: 400, error_code: "invalid_credentials", msg: "Invalid login credentials" });
    }
    const now = Math.floor(Date.now() / 1000);
    const exp = now + 3600;
    const access_token = sign({ sub: user.id, aud: "authenticated", role: "authenticated", email, iat: now, exp });
    return send(res, 200, {
      access_token,
      token_type: "bearer",
      expires_in: 3600,
      expires_at: exp,
      refresh_token: `refresh-${user.id}`,
      user: userObject(email, user),
    });
  }

  if (url.pathname === "/auth/v1/user") {
    const payload = verify((req.headers.authorization ?? "").replace(/^Bearer /, ""));
    const hit = payload ? byId(payload.sub) : null;
    if (!hit) return send(res, 401, { code: 401, error_code: "bad_jwt", msg: "invalid JWT" });
    return send(res, 200, userObject(hit[0], hit[1]));
  }

  if (url.pathname === "/auth/v1/logout") return send(res, 204);

  if (url.pathname === "/rest/v1/profiles") {
    const id = (url.searchParams.get("id") ?? "").replace(/^eq\./, "");
    const hit = byId(id);
    const rows = hit ? [{ id: hit[1].id, role: hit[1].role, office: hit[1].office, alias: hit[1].alias }] : [];
    const single = (req.headers.accept ?? "").includes("vnd.pgrst.object");
    if (single) return send(res, rows.length ? 200 : 406, rows[0] ?? { code: "PGRST116", message: "no rows" });
    return send(res, 200, rows);
  }
  if (url.pathname === "/rest/v1/buildings") return send(res, 200, BUILDINGS);
  if (url.pathname.startsWith("/rest/v1/")) return send(res, 200, []);

  return send(res, 404, { message: "not faked" });
});

// Realtime is not faked: refusing the upgrade makes the client retry quietly, and the chat works without it.
server.on("upgrade", (_req, socket) => socket.destroy());

server.listen(PORT, "127.0.0.1", () => console.log(`fake supabase on http://127.0.0.1:${PORT}`));
