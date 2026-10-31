import { describe, expect, it } from "vitest";
import {
  OUTBOX_LIMIT,
  filterOutbox,
  filterStatuses,
  mergeOutbox,
  outboxTone,
  sortOutbox,
  statusCounts,
  type OutboxMessage,
} from "../view";

const row = (id: string, status: string, created_at = "2026-11-08T10:00:00Z", o: Partial<OutboxMessage> = {}): OutboxMessage => ({
  id,
  alias: null,
  body: "",
  channel: "email",
  created_at,
  error: null,
  flags: [],
  kind: "email",
  priority: null,
  provider_id: null,
  request_id: null,
  status,
  subject: "s",
  to_address: "demo@example.test",
  ...o,
});

describe("outboxTone", () => {
  it("gives every known status a tone and an unknown one a neutral tone", () => {
    expect(outboxTone("sent")).toBe("ok");
    expect(outboxTone("simulated")).toBe("info");
    expect(outboxTone("deferred")).toBe("warn");
    expect(outboxTone("rejected")).toBe("danger");
    expect(outboxTone("failed")).toBe("danger");
    expect(outboxTone("queued")).toBe("neutral");
    expect(outboxTone("brand_new")).toBe("neutral");
  });
});

describe("merge and sort", () => {
  it("sorts newest first and tolerates an unreadable date", () => {
    const rows = sortOutbox([row("a", "sent", "2026-11-08T09:00:00Z"), row("b", "sent", "2026-11-08T11:00:00Z"), row("c", "sent", "bad")]);
    expect(rows.map((r) => r.id)).toEqual(["b", "a", "c"]);
  });

  it("replaces a row with the same id (a status change) and adds a new one on top", () => {
    const start = [row("a", "queued", "2026-11-08T09:00:00Z")];
    const updated = mergeOutbox(start, row("a", "sent", "2026-11-08T09:00:00Z"));
    expect(updated).toHaveLength(1);
    expect(updated[0]?.status).toBe("sent");
    const added = mergeOutbox(updated, row("b", "rejected", "2026-11-08T10:00:00Z"));
    expect(added.map((r) => r.id)).toEqual(["b", "a"]);
  });

  it("keeps at most the newest rows", () => {
    let rows: OutboxMessage[] = [];
    for (let i = 0; i < OUTBOX_LIMIT + 5; i++) rows = mergeOutbox(rows, row(`r${i}`, "sent", new Date(Date.UTC(2026, 10, 8, 0, 0, i)).toISOString()));
    expect(rows).toHaveLength(OUTBOX_LIMIT);
    expect(rows[0]?.id).toBe(`r${OUTBOX_LIMIT + 4}`);
  });
});

describe("filters", () => {
  const rows = [row("1", "sent"), row("2", "rejected"), row("3", "simulated"), row("4", "rejected"), row("5", "paused")];

  it("counts by status with the total under all", () => {
    expect(statusCounts(rows)).toEqual({ all: 5, sent: 1, rejected: 2, simulated: 1, paused: 1 });
  });

  it("offers the known statuses in order, then any other status present", () => {
    expect(filterStatuses(rows)).toEqual(["sent", "simulated", "deferred", "rejected", "failed", "queued", "paused"]);
    expect(filterStatuses([])).toEqual(["sent", "simulated", "deferred", "rejected", "failed", "queued"]);
  });

  it("filters by status and keeps everything for all", () => {
    expect(filterOutbox(rows, "rejected").map((r) => r.id)).toEqual(["2", "4"]);
    expect(filterOutbox(rows, "all")).toHaveLength(5);
    expect(filterOutbox(rows, "deferred")).toEqual([]);
  });
});
