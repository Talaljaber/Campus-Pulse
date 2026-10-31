import { describe, expect, it } from "vitest";
import { applyIncident, incidentView } from "@/lib/incidents";
import type { IncidentRow } from "@/lib/repos/incidents";
import type { PredictionRow } from "@/lib/repos/predictions";
import type { RequestRow, ReviewRow } from "@/lib/repos/requests";
import type { TicketLinkRow, TicketRow } from "@/lib/repos/tickets";
import { buildDetail } from "../detail";
import { evidenceFromPrediction, explanationFromPrediction, tierOf } from "../explanation";
import { WATCHED_FLAGS, buildFlagEvents, knownFlags } from "../flags";
import { buildReviewViews, mayNeedReview, withoutReview } from "../review";
import { staffErrorKind } from "../service";
import {
  applyTicketOut,
  durationParts,
  filterTickets,
  mergeLive,
  slaState,
  sortTickets,
  upsertTicket,
  withLinks,
} from "../tickets";

const NOW = new Date("2026-11-08T10:00:00Z");
const H = 3_600_000;

const ticket = (o: Partial<TicketRow> = {}): TicketRow => ({
  id: "t1",
  request_id: "r1",
  incident_id: null,
  office: "it",
  category: "IT Support",
  priority: "medium",
  status: "open",
  provisional: false,
  title: "Wi-Fi",
  body: "",
  sla_due_at: new Date(NOW.getTime() + 10 * H).toISOString(),
  escalated_at: null,
  resolved_at: null,
  created_at: "2026-11-08T08:00:00Z",
  tags: [],
  ...o,
});

const prediction = (o: Partial<PredictionRow> = {}): PredictionRow => ({
  id: "p1",
  request_id: "r1",
  category: "IT Support",
  priority: "medium",
  artifact_version: "v1",
  core: { evidence: { spans: [{ type: "deadline_today", span: "today", lang: "en" }, { nope: 1 }] } },
  cost_usd: 0.0012,
  created_at: "2026-11-08T09:00:00Z",
  explanation: {
    top_tokens: [["wifi", 0.6], ["bad", "x"], ["down", 0.3]],
    neighbors: [
      { text: "wifi down", category: "IT Support", priority: "high", sim: 0.9, source: "memory", created_at: "2026-11-08T09:00:00Z" },
      { text: "broken", category: "IT Support", priority: "high", sim: 0.5, source: "weird" },
    ],
    counterfactual: { drop: "wifi", category: "Facilities", priority: "low" },
    trace: { clarified: true },
  },
  flags: [],
  latency_ms: 42,
  models_used: null,
  p_cat: null,
  p_pri: null,
  per_model: null,
  set_cat: ["IT Support", "Facilities"],
  set_pri: ["medium"],
  tier: "tier0",
  ...o,
});

const request = (o: Partial<RequestRow> = {}): RequestRow => ({
  id: "r1",
  alias: "talal",
  building_id: "M",
  conversation_id: null,
  core: null,
  created_at: "2026-11-08T08:55:00Z",
  input_mode: "voice",
  is_arabizi: false,
  lang: "en",
  location_source: null,
  model_text: null,
  raw_text: "the wifi is down",
  room: "M 214",
  simulated: false,
  stated_urgency: null,
  status: "decided",
  text_norm: null,
  truncated: false,
  ...o,
});

describe("ticket ordering and filtering", () => {
  it("puts active tickets by SLA first, then finished ones newest first, without mutating the input", () => {
    const a = ticket({ id: "a", sla_due_at: new Date(NOW.getTime() + 5 * H).toISOString() });
    const b = ticket({ id: "b", sla_due_at: new Date(NOW.getTime() - 2 * H).toISOString() });
    const done1 = ticket({ id: "d1", status: "resolved", created_at: "2026-11-07T00:00:00Z" });
    const done2 = ticket({ id: "d2", status: "closed", created_at: "2026-11-08T00:00:00Z" });
    const input = [done1, a, done2, b];
    expect(sortTickets(input).map((t) => t.id)).toEqual(["b", "a", "d2", "d1"]);
    expect(input.map((t) => t.id)).toEqual(["d1", "a", "d2", "b"]);
  });

  it("filters active, done and all", () => {
    const list = [ticket({ id: "a" }), ticket({ id: "b", status: "escalated" }), ticket({ id: "c", status: "resolved" }), ticket({ id: "d", status: "merged" })];
    expect(filterTickets(list, "active").map((t) => t.id)).toEqual(["a", "b"]);
    expect(filterTickets(list, "done").map((t) => t.id)).toEqual(["c", "d"]);
    expect(filterTickets(list, "all")).toHaveLength(4);
  });

  it("upserts by id", () => {
    const list = [ticket({ id: "a" })];
    expect(upsertTicket(list, ticket({ id: "b" }))).toHaveLength(2);
    expect(upsertTicket(list, ticket({ id: "a", title: "new" }))[0]!.title).toBe("new");
  });
});

describe("links and live merges", () => {
  const link = (o: Partial<TicketLinkRow>): TicketLinkRow => ({
    ticket_id: "t1",
    sink: "linear",
    external_id: "CP-1",
    external_url: "https://linear.app/x/CP-1",
    created_at: "",
    last_error: null,
    last_synced_at: null,
    ...o,
  });

  it("attaches the Linear link and leaves others null", () => {
    const views = withLinks([ticket(), ticket({ id: "t2" })], [link({})]);
    expect(views[0]!.link).toEqual({ id: "CP-1", url: "https://linear.app/x/CP-1" });
    expect(views[1]!.link).toBeNull();
  });

  it("keeps the known link when a live update arrives", () => {
    const views = withLinks([ticket()], [link({})]);
    const next = mergeLive(views, ticket({ status: "in_progress" }));
    expect(next[0]!.status).toBe("in_progress");
    expect(next[0]!.link?.id).toBe("CP-1");
  });

  it("applyTicketOut keeps the office code from the database row", () => {
    const merged = applyTicketOut(ticket({ office: "registrar" }), {
      status: "resolved",
      resolved_at: "2026-11-08T10:00:00Z",
      escalated_at: null,
      provisional: false,
      priority: "high",
      sla_due_at: "2026-11-09T10:00:00Z",
    });
    expect(merged.office).toBe("registrar");
    expect(merged.status).toBe("resolved");
    expect(merged.priority).toBe("high");
  });
});

describe("sla", () => {
  it("is overdue, soon, ok or done", () => {
    const at = (h: number, status = "open") => slaState({ status, sla_due_at: new Date(NOW.getTime() + h * H).toISOString() }, NOW).kind;
    expect(at(-1)).toBe("overdue");
    expect(at(3)).toBe("soon");
    expect(at(5)).toBe("ok");
    expect(at(-5, "resolved")).toBe("done");
  });

  it("splits a span into a unit and a count", () => {
    expect(durationParts(30_000)).toEqual({ unit: "minutes", n: 1 });
    expect(durationParts(-5 * 60_000)).toEqual({ unit: "minutes", n: 5 });
    expect(durationParts(3 * H)).toEqual({ unit: "hours", n: 3 });
    expect(durationParts(50 * H)).toEqual({ unit: "days", n: 2 });
  });
});

describe("explanation from a stored prediction", () => {
  it("maps the stored shape to the API shape and drops malformed entries", () => {
    const e = explanationFromPrediction(prediction())!;
    expect(e.top_tokens).toEqual([["wifi", 0.6], ["down", 0.3]]);
    expect(e.neighbors).toHaveLength(1);
    expect(e.neighbors[0]).toMatchObject({ label: "IT Support", source: "memory", sim: 0.9 });
    expect(e.counterfactual).toEqual({ drop: "wifi", category: "Facilities", priority: "low" });
    expect(e.trace).toMatchObject({ sets: { cat: 2, pri: 1 }, clarified: true, cost_usd: 0.0012, latency_ms: 42, artifact_version: "v1" });
  });

  it("is null without an explanation and tolerates a missing trace or counterfactual", () => {
    expect(explanationFromPrediction(prediction({ explanation: null }))).toBeNull();
    const e = explanationFromPrediction(prediction({ explanation: { top_tokens: [], neighbors: [] } }))!;
    expect(e.counterfactual).toBeNull();
    expect(e.trace.clarified).toBe(false);
  });

  it("reads evidence spans and the tier", () => {
    expect(evidenceFromPrediction(prediction())).toEqual([{ type: "deadline_today", span: "today" }]);
    expect(evidenceFromPrediction({ core: null })).toEqual([]);
    expect(tierOf({ tier: "human" })).toBe("human");
    expect(tierOf({ tier: "odd" })).toBeUndefined();
    expect(tierOf({ tier: null })).toBeUndefined();
  });
});

describe("review views", () => {
  const review = (o: Partial<ReviewRow> = {}): ReviewRow => ({
    id: "rv1",
    prediction_id: "p1",
    reason: "x",
    status: "open",
    created_at: "2026-11-08T09:00:00Z",
    corrected_category: null,
    corrected_priority: null,
    note: null,
    resolved_at: null,
    reviewer_id: null,
    ...o,
  });

  it("joins review rows with their prediction and request", () => {
    const [v] = buildReviewViews([review()], [prediction()], [request()]);
    expect(v).toMatchObject({ predictionId: "p1", requestId: "r1", text: "the wifi is down", category: "IT Support", distress: false });
    expect(v!.setCat).toEqual(["IT Support", "Facilities"]);
    expect(v!.explanation).not.toBeNull();
  });

  it("still lists an item whose prediction or request the caller cannot read", () => {
    const [noPrediction] = buildReviewViews([review()], [], []);
    expect(noPrediction).toMatchObject({ text: null, category: null, explanation: null, requestId: null });
    const [noRequest] = buildReviewViews([review()], [prediction()], []);
    expect(noRequest).toMatchObject({ text: null, category: "IT Support" });
  });

  it("marks distress and removes a decided item", () => {
    const views = buildReviewViews([review(), review({ id: "rv2", prediction_id: "p2" })], [prediction({ flags: ["distress"] }), prediction({ id: "p2" })], [request()]);
    expect(views[0]!.distress).toBe(true);
    expect(withoutReview(views, "p1").map((v) => v.id)).toEqual(["rv2"]);
  });

  it("knows which new predictions may need review", () => {
    expect(mayNeedReview(["needs_review"])).toBe(true);
    expect(mayNeedReview(["distress"])).toBe(true);
    expect(mayNeedReview(["safety"])).toBe(false);
  });
});

describe("flag events", () => {
  it("keeps only watched flags, newest first, with the request text", () => {
    const events = buildFlagEvents(
      [
        prediction({ id: "a", flags: ["injection_attempt", "safety"], created_at: "2026-11-08T09:00:00Z" }),
        prediction({ id: "b", flags: ["safety"] }),
        prediction({ id: "c", flags: ["urgency_unsupported"], created_at: "2026-11-08T09:30:00Z" }),
      ],
      [request()],
    );
    expect(events.map((e) => e.id)).toEqual(["c", "a"]);
    expect(events[1]!.flags).toEqual(["injection_attempt"]);
    expect(events[1]!.text).toBe("the wifi is down");
    expect(WATCHED_FLAGS).toContain("priority_gaming_suspected");
  });

  it("knownFlags drops names the dictionary cannot print", () => {
    expect(knownFlags(["safety", "from_the_future"])).toEqual(["safety"]);
  });
});

describe("request detail", () => {
  it("uses the newest prediction as the current decision", () => {
    const d = buildDetail(request(), [prediction({ id: "new" }), prediction({ id: "old" })]);
    expect(d.prediction?.id).toBe("new");
    expect(d.inputMode).toBe("voice");
    expect(buildDetail(request(), []).prediction).toBeNull();
  });
});

describe("incidents", () => {
  const row = (o: Partial<IncidentRow>): IncidentRow => ({
    id: "i1",
    building_id: "M",
    category: "IT Support",
    created_at: "",
    office: "it",
    opened_at: "2026-11-08T09:00:00Z",
    priority: "high",
    report_count: 3,
    resolved_at: null,
    status: "open",
    title: "Wi-Fi outage",
    ...o,
  });

  it("applies live rows: new, bump, resolve", () => {
    let list: IncidentRow[] = [];
    list = applyIncident(list, row({}));
    list = applyIncident(list, row({ id: "i2", opened_at: "2026-11-08T09:30:00Z" }));
    expect(list.map((i) => i.id)).toEqual(["i2", "i1"]);
    list = applyIncident(list, row({ report_count: 6 }));
    expect(list.find((i) => i.id === "i1")!.report_count).toBe(6);
    list = applyIncident(list, row({ status: "resolved" }));
    expect(list.map((i) => i.id)).toEqual(["i2"]);
  });

  it("maps a row to the view", () => {
    expect(incidentView(row({}))).toEqual({
      id: "i1",
      buildingId: "M",
      category: "IT Support",
      title: "Wi-Fi outage",
      priority: "high",
      reportCount: 3,
      openedAt: "2026-11-08T09:00:00Z",
    });
  });
});

describe("staffErrorKind", () => {
  const fail = (status: number, code: string, waking = false) =>
    ({ ok: false, status, code, error: "", details: null, waking }) as Parameters<typeof staffErrorKind>[0];
  it("maps status and code to a dictionary kind", () => {
    expect(staffErrorKind(fail(401, "unauthenticated"))).toBe("session");
    expect(staffErrorKind(fail(403, "forbidden"))).toBe("forbidden");
    expect(staffErrorKind(fail(404, "not_found"))).toBe("notFound");
    expect(staffErrorKind(fail(503, "ai_waking", true))).toBe("waking");
    expect(staffErrorKind(fail(500, "internal_error"))).toBe("generic");
  });
});
