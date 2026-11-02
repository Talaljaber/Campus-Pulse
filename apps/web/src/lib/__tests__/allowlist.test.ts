import { describe, expect, it } from "vitest";
import { matchAllowed } from "@/lib/ai/allowlist";

const ID = "5b0e7c52-3f0a-4d8e-9c41-0a1b2c3d0001";

describe("matchAllowed", () => {
  it.each([
    ["POST", ["triage"]],
    ["POST", ["triage", ID, "clarify"]],
    ["GET", ["explain", ID, "counterfactual"]],
    ["POST", ["feedback"]],
    ["POST", ["tickets", ID, "status"]],
    ["POST", ["tickets", ID, "forward"]],
    ["POST", ["tickets", ID, "comments"]],
    ["POST", ["tickets", ID, "priority"]],
    ["POST", ["tickets", ID, "student-action"]],
    ["GET", ["reviews"]],
    ["POST", ["reviews", ID, "forward"]],
    ["GET", ["incidents"]],
    ["POST", ["incidents", ID, "resolve"]],
    ["GET", ["insights", "recurring"]],
    ["POST", ["redteam", "run"]],
    ["GET", ["metrics"]],
    ["POST", ["batch"]],
    ["GET", ["health"]],
    ["POST", ["admin", "simulate"]],
    ["POST", ["admin", "reindex"]],
    ["POST", ["announcements"]],
    ["POST", ["announcements", ID, "archive"]],
  ])("allows %s %j", (method, segments) => {
    expect(matchAllowed(method, segments)).not.toBeNull();
  });

  it("marks only health as public", () => {
    expect(matchAllowed("GET", ["health"])?.public).toBe(true);
    expect(matchAllowed("GET", ["metrics"])?.public).toBe(false);
  });

  it.each([
    ["GET", ["triage"]],
    ["GET", ["tickets", ID, "comments"]],
    ["POST", ["tickets", ID, "priority", "x"]],
    ["GET", ["tickets", ID, "student-action"]],
    ["POST", ["health"]],
    ["GET", ["admin", "simulate"]],
    ["POST", ["admin", "users"]],
    ["POST", ["integrations", "linear", "webhook"]],
    ["GET", ["incidents", ID, "resolve"]],
    ["POST", ["reviews"]],
    ["GET", ["reviews", ID, "forward"]],
    ["POST", ["reviews", "..", "forward"]],
    ["POST", ["triage", "..", "metrics"]],
    ["POST", ["triage", "a.b", "clarify"]],
    ["POST", ["triage", "a%2Fb", "clarify"]],
    ["POST", ["triage", "a/b", "clarify"]],
    ["DELETE", ["triage"]],
    ["GET", []],
    ["GET", ["announcements"]],
    ["POST", ["announcements", ID]],
    ["GET", ["announcements", ID, "archive"]],
    ["POST", ["announcements", "..", "archive"]],
    ["POST", ["announcements", ID, "delete"]],
  ])("rejects %s %j", (method, segments) => {
    expect(matchAllowed(method, segments)).toBeNull();
  });
});
