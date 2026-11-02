import { describe, expect, it } from "vitest";
import { translate } from "@/i18n";
import { formatDuration, isRunning, timeLeft } from "../clock";
import { ticketNumber } from "../number";
import { staffStatusOptions } from "../transitions";

const t = (key: Parameters<typeof translate>[1], vars?: Record<string, string | number>) => translate("en", key, vars);
const DUE = "2026-11-08T10:00:00Z";
const DUE_MS = new Date(DUE).getTime();
const MIN = 60_000;

describe("isRunning and timeLeft", () => {
  it("runs while new or in progress, stops for solved, closed and merged", () => {
    expect(["new", "in_progress"].every(isRunning)).toBe(true);
    expect(["solved", "closed", "merged"].some(isRunning)).toBe(false);
    for (const s of ["solved", "closed", "merged"]) expect(timeLeft(DUE, s, DUE_MS - 5 * MIN)).toEqual({ state: "stopped", ms: 0 });
  });

  it("is still running exactly at the deadline and overdue one millisecond later", () => {
    expect(timeLeft(DUE, "new", DUE_MS)).toEqual({ state: "running", ms: 0 });
    expect(timeLeft(DUE, "in_progress", DUE_MS + 1)).toEqual({ state: "overdue", ms: -1 });
    expect(timeLeft(DUE, "new", DUE_MS - 90 * MIN)).toEqual({ state: "running", ms: 90 * MIN });
  });

  it("treats an unreadable deadline as stopped instead of overdue", () => {
    expect(timeLeft("not a date", "new", 0).state).toBe("stopped");
  });
});

describe("formatDuration", () => {
  it("writes minutes, hours with padded minutes, and days", () => {
    expect(formatDuration(5 * MIN, t)).toBe("5 min");
    expect(formatDuration(65 * MIN, t)).toBe("1 h 05 min");
    expect(formatDuration(59 * MIN + 1, t)).toBe("1 h 00 min");
    expect(formatDuration((26 * 60 + 10) * MIN, t)).toBe("1 d 2 h");
  });

  it("says overdue by and never shows 0 min", () => {
    expect(formatDuration(-20 * MIN, t)).toBe("overdue by 20 min");
    expect(formatDuration(0, t)).toBe("1 min");
  });

  it("works in Arabic", () => {
    expect(formatDuration(-20 * MIN, (k, v) => translate("ar", k, v))).toBe("متأخر 20 دقيقة");
  });
});

describe("ticketNumber", () => {
  it("is the first 8 hex characters of the id, upper case, without dashes", () => {
    expect(ticketNumber("5b0e7c52-3f0a-4d8e-9c41-0a1b2c3d0001")).toBe("5B0E7C52");
    expect(ticketNumber("abc")).toBe("ABC");
  });
});

describe("staffStatusOptions", () => {
  it("mirrors the state machine (set in_progress, solved, closed, reopen)", () => {
    expect(staffStatusOptions("new")).toEqual(["in_progress", "solved", "closed"]);
    expect(staffStatusOptions("in_progress")).toEqual(["solved", "closed"]);
    expect(staffStatusOptions("solved")).toEqual(["in_progress", "closed"]);
    expect(staffStatusOptions("closed")).toEqual(["in_progress"]);
  });

  it("offers nothing for a merged or unknown ticket, and never the current status", () => {
    expect(staffStatusOptions("merged")).toEqual([]);
    expect(staffStatusOptions("weird")).toEqual([]);
    for (const s of ["new", "in_progress", "solved", "closed"]) expect(staffStatusOptions(s)).not.toContain(s);
  });
});
