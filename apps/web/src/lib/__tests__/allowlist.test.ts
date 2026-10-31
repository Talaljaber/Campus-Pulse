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
    ["GET", ["incidents"]],
    ["POST", ["incidents", ID, "resolve"]],
    ["GET", ["insights", "recurring"]],
    ["POST", ["redteam", "run"]],
    ["GET", ["metrics"]],
    ["POST", ["batch"]],
    ["GET", ["health"]],
    ["POST", ["admin", "simulate"]],
    ["POST", ["admin", "reindex"]],
  ])("allows %s %j", (method, segments) => {
    expect(matchAllowed(method, segments)).not.toBeNull();
  });

  it("marks only health as public", () => {
    expect(matchAllowed("GET", ["health"])?.public).toBe(true);
    expect(matchAllowed("GET", ["metrics"])?.public).toBe(false);
  });

  it.each([
    ["GET", ["triage"]],
    ["POST", ["health"]],
    ["GET", ["admin", "simulate"]],
    ["POST", ["admin", "users"]],
    ["POST", ["integrations", "linear", "webhook"]],
    ["GET", ["incidents", ID, "resolve"]],
    ["POST", ["triage", "..", "metrics"]],
    ["POST", ["triage", "a.b", "clarify"]],
    ["POST", ["triage", "a%2Fb", "clarify"]],
    ["POST", ["triage", "a/b", "clarify"]],
    ["DELETE", ["triage"]],
    ["GET", []],
  ])("rejects %s %j", (method, segments) => {
    expect(matchAllowed(method, segments)).toBeNull();
  });
});
