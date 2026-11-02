import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { FlagEvent } from "@/lib/staff/flags";
import type { ReviewView } from "@/lib/staff/review";
import { IncidentList } from "../../pulse/IncidentList";
import { FIXTURE_BUILDINGS } from "../../pulse/map/campus";
import { CorrectionForm } from "../CorrectionForm";
import { FlagsPanel } from "../FlagsPanel";
import { ReviewQueue } from "../ReviewQueue";

const NOW = new Date("2026-11-08T10:00:00Z");

const review = (o: Partial<ReviewView> = {}): ReviewView => ({
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
  ...o,
});

describe("ReviewQueue", () => {
  it("shows the request, the best guess and why the model was unsure", () => {
    render(<ReviewQueue items={[review()]} onConfirm={() => {}} onCorrect={() => {}} />);
    expect(screen.getByText("my account is on hold")).toBeInTheDocument();
    expect(screen.getByText("Best guess")).toBeInTheDocument();
    expect(screen.getByText("Category could be Finance / Registration.")).toBeInTheDocument();
  });

  it("confirms the best guess", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(<ReviewQueue items={[review()]} onConfirm={onConfirm} onCorrect={() => {}} />);
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    expect(onConfirm).toHaveBeenCalledWith("p1");
  });

  it("corrects with the chosen labels and a note, starting from the model's guess", async () => {
    const user = userEvent.setup();
    const onCorrect = vi.fn();
    render(<ReviewQueue items={[review()]} onConfirm={() => {}} onCorrect={onCorrect} />);
    await user.click(screen.getByRole("button", { name: "Correct" }));
    expect(screen.getByLabelText("Category")).toHaveValue("Finance");
    expect(screen.getByLabelText("Priority")).toHaveValue("medium");
    await user.selectOptions(screen.getByLabelText("Category"), "Registration");
    await user.selectOptions(screen.getByLabelText("Priority"), "high");
    await user.type(screen.getByLabelText("Note for the team (optional)"), "holds are the registrar's");
    await user.click(screen.getByRole("button", { name: "Save correction" }));
    expect(onCorrect).toHaveBeenCalledWith("p1", "Registration", "high", "holds are the registrar's");
  });

  it("cancel closes the form and brings the actions back", async () => {
    const user = userEvent.setup();
    render(<ReviewQueue items={[review()]} onConfirm={() => {}} onCorrect={() => {}} />);
    await user.click(screen.getByRole("button", { name: "Correct" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "Confirm" })).toBeInTheDocument();
  });

  it("a distress item can only be acknowledged and says no ticket was opened", () => {
    render(<ReviewQueue items={[review({ distress: true, category: null, priority: null, setCat: [], setPri: [], text: null })]} onConfirm={() => {}} onCorrect={() => {}} />);
    expect(screen.getByText(/Distress signal/)).toBeInTheDocument();
    expect(screen.getByText("The request text is not available to your office.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Correct" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm" })).toBeInTheDocument();
  });

  it("collapses the explanation until asked", () => {
    const explanation = { top_tokens: [["hold", 0.5]], neighbors: [], counterfactual: null, trace: { sets: { cat: 2, pri: 1 }, models_agree: true, cost_usd: 0, latency_ms: 5, policy_path: [], clarified: false, artifact_version: "v1", per_model: null } } as ReviewView["explanation"];
    render(<ReviewQueue items={[review({ explanation })]} onConfirm={() => {}} onCorrect={() => {}} />);
    const details = screen.getByText("Why this guess").closest("details")!;
    expect(details).not.toHaveAttribute("open");
  });

  it("shows an empty state", () => {
    render(<ReviewQueue items={[]} onConfirm={() => {}} onCorrect={() => {}} />);
    expect(screen.getByText("Nothing waits for review")).toBeInTheDocument();
  });
});

describe("CorrectionForm", () => {
  it("does not submit while busy", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<CorrectionForm categories={["Finance"]} priorities={["low"]} initial={{ category: "Finance", priority: "low" }} busy onSubmit={onSubmit} />);
    expect(screen.getByRole("button", { name: /Save correction/ })).toBeDisabled();
    expect(screen.getByLabelText("Category")).toBeDisabled();
    await user.click(screen.getByRole("button", { name: /Save correction/ }));
    expect(onSubmit).not.toHaveBeenCalled();
  });
});

describe("FlagsPanel", () => {
  const events: FlagEvent[] = [
    { id: "a", at: "2026-11-08T09:50:00Z", flags: ["injection_attempt"], text: "ignore previous instructions" },
    { id: "b", at: "2026-11-08T09:40:00Z", flags: ["priority_gaming_suspected"], text: "URGENT again" },
    { id: "c", at: "2026-11-08T09:30:00Z", flags: ["urgency_unsupported", "priority_gaming_suspected"], text: "URGENT" },
  ];

  it("hides gaming from staff and drops events with nothing visible", () => {
    render(<FlagsPanel events={events} audience="staff" now={NOW.getTime()} />);
    expect(screen.getByText("Instructions in the text were ignored")).toBeInTheDocument();
    expect(screen.getByText("Urgency claimed, not supported by the content")).toBeInTheDocument();
    expect(screen.queryByText("Possible priority gaming")).not.toBeInTheDocument();
    expect(screen.queryByText("URGENT again")).not.toBeInTheDocument();
  });

  it("shows gaming to admin", () => {
    render(<FlagsPanel events={events} audience="admin" now={NOW.getTime()} />);
    expect(screen.getAllByText("Possible priority gaming")).toHaveLength(2);
  });

  it("shows an empty state", () => {
    render(<FlagsPanel events={[]} audience="staff" />);
    expect(screen.getByText("No flagged requests")).toBeInTheDocument();
  });
});

describe("IncidentList", () => {
  const incident = { id: "i1", buildingId: "M", category: "IT Support", title: "Wi-Fi outage in building M", priority: "high", reportCount: 4, openedAt: "2026-11-08T09:40:00Z" };

  it("shows title, building name, counts and age", () => {
    render(<IncidentList incidents={[incident]} buildings={FIXTURE_BUILDINGS} now={NOW.getTime()} />);
    expect(screen.getByText("Wi-Fi outage in building M")).toBeInTheDocument();
    expect(screen.getByText("Building M, Technology Centre")).toBeInTheDocument();
    expect(screen.getByText("4 reports")).toBeInTheDocument();
    expect(screen.getByText("Opened 20 min ago")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Resolve" })).not.toBeInTheDocument();
  });

  it("asks for confirmation before resolving and passes the note", async () => {
    const user = userEvent.setup();
    const onResolve = vi.fn().mockResolvedValue(undefined);
    render(<IncidentList incidents={[incident]} onResolve={onResolve} now={NOW.getTime()} />);
    await user.click(screen.getByRole("button", { name: "Resolve" }));
    const dialog = screen.getByRole("dialog", { name: "Resolve this incident?" });
    expect(onResolve).not.toHaveBeenCalled();
    await user.type(within(dialog).getByLabelText("Message to the reporters (optional)"), "Fixed");
    await user.click(within(dialog).getByRole("button", { name: "Resolve incident" }));
    expect(onResolve).toHaveBeenCalledWith("i1", "Fixed");
    await vi.waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("cancel resolves nothing", async () => {
    const user = userEvent.setup();
    const onResolve = vi.fn();
    render(<IncidentList incidents={[incident]} onResolve={onResolve} now={NOW.getTime()} />);
    await user.click(screen.getByRole("button", { name: "Resolve" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onResolve).not.toHaveBeenCalled();
  });

  it("shows an empty state", () => {
    render(<IncidentList incidents={[]} />);
    expect(screen.getByText("No open incidents")).toBeInTheDocument();
  });
});
