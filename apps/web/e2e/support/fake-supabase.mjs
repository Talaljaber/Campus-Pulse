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

// Rows for the staff and pulse pages. They are tiny on purpose: one overdue ticket in the staff
// office, one in another office (must never show for staff), one finished, a review item, an incident.
const ago = (h) => new Date(Date.now() - h * 3_600_000).toISOString();
const ahead = (h) => new Date(Date.now() + h * 3_600_000).toISOString();
const ticketRow = (o) => ({
  incident_id: null,
  tags: [],
  provisional: false,
  body: "",
  escalated_at: null,
  resolved_at: null,
  created_at: ago(5),
  ...o,
});
const explanation = {
  top_tokens: [["hold", 0.55], ["fees", 0.3]],
  neighbors: [],
  counterfactual: null,
  trace: {},
};
const outboxRow = (o) => ({ channel: "email", alias: null, request_id: null, body: "", priority: null, flags: [], error: null, provider_id: null, ...o });
const TABLES = {
  tickets: [
    ticketRow({ id: "t-1", request_id: "r-1", office: "it", category: "IT Support", priority: "high", status: "open", title: "Wi-Fi is down in building M", sla_due_at: ago(3) }),
    ticketRow({ id: "t-2", request_id: "r-3", office: "finance", category: "Finance", priority: "medium", status: "open", title: "Fee receipt missing", sla_due_at: ahead(40) }),
    ticketRow({ id: "t-3", request_id: "r-4", office: "it", category: "IT Support", priority: "low", status: "resolved", title: "Reset my e-learning password", sla_due_at: ahead(100), resolved_at: ago(1) }),
  ],
  ticket_links: [{ ticket_id: "t-1", sink: "linear", external_id: "CP-47", external_url: "https://linear.app/campuspulse-demo/issue/CP-47", created_at: ago(5), last_error: null, last_synced_at: null }],
  requests: [
    { id: "r-5", alias: "sim-01", raw_text: "the projector in A 101 is broken", lang: "en", input_mode: "text", building_id: "A", room: "A 101", simulated: true, status: "decided", created_at: ago(0.5), truncated: false },
    { id: "r-1", alias: "talal", raw_text: "the wifi in building M is down again", lang: "en", input_mode: "voice", building_id: "M", room: "M 214", simulated: false, status: "decided", created_at: ago(5), truncated: false },
    { id: "r-2", alias: "talal", raw_text: "my account is on hold after paying fees", lang: "en", input_mode: "text", building_id: null, room: null, simulated: false, status: "human_review", created_at: ago(1), truncated: false },
  ],
  predictions: [
    { id: "p-5", request_id: "r-5", category: "Facilities", priority: "medium", flags: [], set_cat: ["Facilities"], set_pri: ["medium"], tier: "tier0", cost_usd: 0, latency_ms: 40, artifact_version: "v1", explanation, core: { evidence: { spans: [] } }, created_at: ago(0.5) },
    { id: "p-1", request_id: "r-1", category: "IT Support", priority: "high", flags: [], set_cat: ["IT Support"], set_pri: ["high"], tier: "tier0", cost_usd: 0, latency_ms: 40, artifact_version: "v1", explanation, core: { evidence: { spans: [] } }, created_at: ago(5) },
    { id: "p-2", request_id: "r-2", category: "Finance", priority: "medium", flags: ["needs_review"], set_cat: ["Finance", "Registration"], set_pri: ["medium"], tier: "tier0", cost_usd: 0, latency_ms: 40, artifact_version: "v1", explanation, core: { evidence: { spans: [] } }, created_at: ago(1) },
  ],
  review_queue: [{ id: "rv-1", prediction_id: "p-2", reason: "ambiguous", status: "open", created_at: ago(1), corrected_category: null, corrected_priority: null, note: null, resolved_at: null, reviewer_id: null }],
  incidents: [{ id: "e4f2a6c8-1b3d-4f5e-8a7c-9b0d1e2f0001", building_id: "M", category: "IT Support", office: "it", title: "Wi-Fi outage in building M", priority: "high", report_count: 4, status: "open", opened_at: ago(0.4), resolved_at: null, created_at: ago(0.4) }],
  outbox: [
    { id: "o-1", kind: "broadcast", channel: "in_app", alias: null, request_id: null, to_address: "", subject: "Wi-Fi in building M: we are on it", body: "", status: "simulated", priority: "high", flags: [], error: null, provider_id: null, created_at: ago(0.2) },
    // The outbox page: one row for each status that matters. Addresses are made up (example.test), never real.
    outboxRow({ id: "o-2", kind: "booking", to_address: "advisor+demo@example.test", subject: "Your advisor slot is booked", status: "sent", created_at: ago(1) }),
    outboxRow({ id: "o-3", kind: "email", to_address: "someone@real.example", subject: "Your password reset link", status: "rejected", error: "recipient is not on the demo allow-list", created_at: ago(2) }),
    outboxRow({ id: "o-4", kind: "email", to_address: "student+demo@example.test", subject: "Ticket update", status: "deferred", error: "daily send cap reached", created_at: ago(3) }),
    outboxRow({ id: "o-5", kind: "alert", to_address: "student+demo@example.test", subject: "Safety alert", status: "failed", error: "smtp timeout", created_at: ago(4) }),
  ],
};

/** Applies PostgREST-style `col=eq.value` and `col=in.(a,b)` filters; everything else (select, order, limit) is ignored. */
function applyFilters(rows, params) {
  let out = rows;
  for (const [col, expr] of params) {
    if (["select", "order", "limit", "offset"].includes(col)) continue;
    if (expr.startsWith("eq.")) out = out.filter((r) => String(r[col]) === expr.slice(3));
    else if (expr.startsWith("in.(")) {
      const set = new Set(expr.slice(4, -1).split(","));
      out = out.filter((r) => set.has(String(r[col])));
    } else if (expr.startsWith("not.is.null")) out = out.filter((r) => r[col] !== null && r[col] !== undefined);
  }
  return out;
}

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
  if (url.pathname.startsWith("/rest/v1/")) {
    const table = url.pathname.slice("/rest/v1/".length);
    let rows = TABLES[table] ?? [];
    // A stand-in for row-level security on tickets: staff only get their own office.
    const caller = verify((req.headers.authorization ?? "").replace(/^Bearer /, ""));
    const me = caller ? byId(caller.sub)?.[1] : null;
    if (table === "tickets" && me?.role === "staff") rows = rows.filter((r) => r.office === me.office);
    return send(res, 200, applyFilters(rows, url.searchParams));
  }

  return send(res, 404, { message: "not faked" });
});

// Realtime is not faked: refusing the upgrade makes the client retry quietly, and the chat works without it.
server.on("upgrade", (_req, socket) => socket.destroy());

server.listen(PORT, "127.0.0.1", () => console.log(`fake supabase on http://127.0.0.1:${PORT}`));
