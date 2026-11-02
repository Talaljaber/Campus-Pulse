import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { LangScope } from "@/i18n";
import type { ReviewView } from "@/lib/staff/review";

const item: ReviewView = {
  id: "rv1",
  predictionId: "p1",
  requestId: "r1",
  createdAt: "2026-11-08T09:00:00Z",
  text: "my account is on hold",
  category: "Finance",
  priority: "medium",
  setCat: ["Finance", "Registration"],
  setPri: ["medium"],
  flags: ["needs_review"],
  distress: false,
  tier: "tier0",
  explanation: null,
  evidence: [],
};
const ready = { load: "ready" as const, reload: vi.fn() };

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), usePathname: () => "/staff/reviews" }));
vi.mock("@/hooks/useSignIn", () => ({ useSignOut: () => vi.fn() }));
vi.mock("@/hooks/useNotifications", () => ({ useNotifications: vi.fn() }));
vi.mock("@/hooks/useAdvisorReviews", () => ({ useAdvisorReviews: () => ({ ...ready, items: [], pending: new Set(), confirm: vi.fn(), forward: vi.fn() }) }));
vi.mock("@/hooks/useFlagEvents", () => ({ useFlagEvents: () => ({ ...ready, events: [] }) }));
vi.mock("@/hooks/useHints", () => ({ useHints: () => ({ ...ready, hints: [] }) }));
vi.mock("@/hooks/useReviewQueue", () => ({
  useReviewQueue: () => ({ ...ready, items: [item], pending: new Set(), confirm: vi.fn(), correct: vi.fn() }),
}));

import { AdvisorScreen } from "../AdvisorScreen";

describe("Corrections page", () => {
  it("shows the unsure predictions first, above the flags and the past corrections", () => {
    render(
      <LangScope lang="en">
        <AdvisorScreen role="staff" alias="it" office="it" />
      </LangScope>,
    );
    const waiting = screen.getByRole("region", { name: "Waiting for review" });
    expect(waiting).toHaveTextContent("my account is on hold");
    expect(screen.getByRole("button", { name: "Confirm" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Correct" })).toBeInTheDocument();
    const flags = screen.getAllByRole("region", { name: "Flagged requests" })[0]!;
    const past = screen.getAllByRole("region", { name: "Past corrections" })[0]!;
    expect(waiting.compareDocumentPosition(flags) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(waiting.compareDocumentPosition(past) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
