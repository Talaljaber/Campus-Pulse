import { describe, expect, it } from "vitest";
import { FIXTURE_BUILDINGS } from "@/components/pulse/map/campus";
import type { IncidentRow } from "@/lib/repos/incidents";
import type { OutboxRow } from "@/lib/repos/outbox";
import type { PredictionBrief } from "@/lib/repos/predictions";
import type { LocatedRequest } from "@/lib/repos/requests";
import { FEED_LIMIT, INITIAL_PULSE, incidentSimulated, pulseReducer, type PulseAction, type PulseState } from "../state";
import { dotsOf, openIncidents, ringsOf } from "../view";

const req = (id: string, o: Partial<LocatedRequest> = {}): LocatedRequest => ({
  id,
  alias: "a",
  building_id: "M",
  room: null,
  status: "decided",
  simulated: false,
  created_at: "2026-11-08T09:00:00Z",
  ...o,
});
const pred = (request_id: string, category = "IT Support", priority = "high"): PredictionBrief => ({
  id: `p-${request_id}`,
  request_id,
  category,
  priority,
  created_at: "2026-11-08T09:00:00Z",
});
const inc = (o: Partial<IncidentRow> = {}): IncidentRow => ({
  id: "i1",
  building_id: "M",
  category: "IT Support",
  created_at: "",
  office: "it",
  opened_at: "2026-11-08T09:10:00Z",
  priority: "high",
  report_count: 3,
  resolved_at: null,
  status: "open",
  title: "Wi-Fi outage",
  ...o,
});
const outbox = (o: Partial<OutboxRow> = {}): OutboxRow => ({
  id: "b1",
  kind: "broadcast",
  channel: "in_app",
  alias: null,
  body: "",
  subject: "We are on it",
  to_address: "",
  status: "sent",
  priority: "high",
  created_at: "2026-11-08T09:20:00Z",
  error: null,
  flags: [],
  provider_id: null,
  request_id: null,
  ...o,
});

const run = (actions: PulseAction[], from: PulseState = INITIAL_PULSE) => actions.reduce(pulseReducer, from);
const snapshot = (o: Partial<Extract<PulseAction, { type: "snapshot" }>> = {}): PulseAction => ({
  type: "snapshot",
  requests: [],
  predictions: [],
  incidents: [],
  broadcasts: [],
  ...o,
});

describe("pulseReducer: requests", () => {
  it("draws a dot only when both the request and its labels are known, in either order", () => {
    const a = run([{ type: "request", row: req("r1") }]);
    expect(dotsOf(a, FIXTURE_BUILDINGS)).toHaveLength(0);
    expect(a.feed).toHaveLength(0);
    const b = run([{ type: "prediction", requestId: "r1", category: "IT Support", priority: "high" }], a);
    expect(dotsOf(b, FIXTURE_BUILDINGS)).toHaveLength(1);
    expect(b.feed.map((e) => e.kind)).toEqual(["request"]);

    const c = run([
      { type: "prediction", requestId: "r2", category: "Finance", priority: "low" },
      { type: "request", row: req("r2") },
    ]);
    expect(dotsOf(c, FIXTURE_BUILDINGS)).toHaveLength(1);
    expect(c.feed).toHaveLength(1);
  });

  it("adds one feed line per request even when the row is delivered again", () => {
    const s = run([
      { type: "request", row: req("r1") },
      { type: "prediction", requestId: "r1", category: "IT Support", priority: "high" },
      { type: "request", row: req("r1", { status: "actioned" }) },
      { type: "prediction", requestId: "r1", category: "IT Support", priority: "high" },
    ]);
    expect(s.feed).toHaveLength(1);
    expect(s.requests.r1!.status).toBe("actioned");
  });

  it("marks simulated requests", () => {
    const s = run([snapshot({ requests: [req("r1", { simulated: true })], predictions: [pred("r1")] })]);
    expect(s.feed[0]!.simulated).toBe(true);
    expect(dotsOf(s, FIXTURE_BUILDINGS)[0]!.simulated).toBe(true);
  });

  it("does not draw a request in an unknown building or one without coordinates", () => {
    const s = run([snapshot({ requests: [req("r1", { building_id: "Z" })], predictions: [pred("r1")] })]);
    expect(dotsOf(s, FIXTURE_BUILDINGS)).toHaveLength(0);
    const noCoords = [{ id: "M", code: "M", name_en: "", name_ar: "", map_x: null, map_y: null }];
    expect(dotsOf(run([snapshot({ requests: [req("r1")], predictions: [pred("r1")] })]), noCoords)).toHaveLength(0);
  });

  it("places a dot at the same spot every time", () => {
    const s = run([snapshot({ requests: [req("r1")], predictions: [pred("r1")] })]);
    expect(dotsOf(s, FIXTURE_BUILDINGS)).toEqual(dotsOf(s, FIXTURE_BUILDINGS));
  });
});

describe("pulseReducer: incidents", () => {
  it("a new incident opens a ring and a feed line, a higher count is a bump, a lower or equal one is not", () => {
    let s = run([{ type: "incident", row: inc(), at: "2026-11-08T09:11:00Z" }]);
    expect(s.feed.map((e) => e.kind)).toEqual(["incident_new"]);
    expect(ringsOf(s, FIXTURE_BUILDINGS)).toHaveLength(1);

    s = run([{ type: "incident", row: inc({ report_count: 6 }), at: "2026-11-08T09:20:00Z" }], s);
    expect(s.feed[0]).toMatchObject({ kind: "incident_bump", count: 6 });
    expect(ringsOf(s, FIXTURE_BUILDINGS)[0]!.reportCount).toBe(6);

    const before = s.feed.length;
    s = run([{ type: "incident", row: inc({ report_count: 6, priority: "medium" }), at: "2026-11-08T09:21:00Z" }], s);
    expect(s.feed).toHaveLength(before);
    expect(ringsOf(s, FIXTURE_BUILDINGS)[0]!.priority).toBe("medium");
  });

  it("a resolved incident leaves the map and the list and adds one resolved line, once", () => {
    let s = run([{ type: "incident", row: inc(), at: "2026-11-08T09:11:00Z" }]);
    s = run([{ type: "incident", row: inc({ status: "resolved" }), at: "2026-11-08T10:00:00Z" }], s);
    expect(ringsOf(s, FIXTURE_BUILDINGS)).toHaveLength(0);
    expect(openIncidents(s)).toHaveLength(0);
    expect(s.feed[0]!.kind).toBe("resolved");
    s = run([{ type: "incident", row: inc({ status: "resolved" }), at: "2026-11-08T10:01:00Z" }], s);
    expect(s.feed.filter((e) => e.kind === "resolved")).toHaveLength(1);
  });

  it("ignores a resolved row for an incident it never saw", () => {
    const s = run([{ type: "incident", row: inc({ status: "resolved" }), at: "x" }]);
    expect(s).toBe(INITIAL_PULSE);
  });

  it("is simulated only while every located request in its building is simulated", () => {
    const sim = run([snapshot({ requests: [req("r1", { simulated: true }), req("r2", { simulated: true })] })]);
    expect(incidentSimulated(sim, "M")).toBe(true);
    const mixed = run([{ type: "request", row: req("r3") }], sim);
    expect(incidentSimulated(mixed, "M")).toBe(false);
    expect(incidentSimulated(INITIAL_PULSE, "M")).toBe(false);
  });

  it("spreads several incidents of one building sideways and filters the list by building", () => {
    const s = run([
      { type: "incident", row: inc({ id: "i1", opened_at: "2026-11-08T09:00:00Z" }), at: "" },
      { type: "incident", row: inc({ id: "i2", opened_at: "2026-11-08T09:30:00Z" }), at: "" },
      { type: "incident", row: inc({ id: "i3", building_id: "A", opened_at: "2026-11-08T09:40:00Z" }), at: "" },
    ]);
    const rings = ringsOf(s, FIXTURE_BUILDINGS);
    const m = rings.filter((r) => r.id !== "i3");
    expect(m[1]!.x - m[0]!.x).toBe(44);
    expect(openIncidents(s).map((i) => i.id)).toEqual(["i3", "i2", "i1"]);
    expect(openIncidents(s, "M").map((i) => i.id)).toEqual(["i2", "i1"]);
  });
});

describe("pulseReducer: snapshot, broadcasts and the feed", () => {
  it("seeds dots, rings and a feed from one snapshot, newest first", () => {
    const s = run([
      snapshot({
        requests: [req("r1", { created_at: "2026-11-08T09:00:00Z" })],
        predictions: [pred("r1")],
        incidents: [inc({ opened_at: "2026-11-08T09:10:00Z" }), inc({ id: "old", status: "resolved" })],
        broadcasts: [outbox(), outbox({ id: "x", kind: "email" })],
      }),
    ]);
    expect(s.feed.map((e) => e.kind)).toEqual(["broadcast", "incident_new", "request"]);
    expect(Object.keys(s.incidents)).toEqual(["i1"]);
  });

  it("a broadcast adds one line and a simulated outbox status is marked", () => {
    let s = run([{ type: "broadcast", row: outbox({ status: "simulated" }) }]);
    expect(s.feed[0]).toMatchObject({ kind: "broadcast", simulated: true, title: "We are on it" });
    s = run([{ type: "broadcast", row: outbox({ status: "sent" }) }], s);
    expect(s.feed).toHaveLength(1);
    s = run([{ type: "broadcast", row: outbox({ id: "other", kind: "alert" }) }], s);
    expect(s.feed).toHaveLength(1);
  });

  it("caps the feed", () => {
    const requests = Array.from({ length: FEED_LIMIT + 10 }, (_, i) => req(`r${i}`, { created_at: new Date(1_700_000_000_000 + i * 1000).toISOString() }));
    const s = run([snapshot({ requests, predictions: requests.map((r) => pred(r.id)) })]);
    expect(s.feed).toHaveLength(FEED_LIMIT);
    expect(s.feed[0]!.id).toBe(`req:r${FEED_LIMIT + 9}`);
  });
});
