import { expect, test } from "@playwright/test";
import { signInAs } from "./support/login";

// P5.8 acceptance. Runs against the mock AI API and the fake Supabase from playwright.config.ts.
// The mock picks its fixture by the exact request text, so the full fixture sentence is typed.
const SENTENCE = "where is the bus timetable for the Madaba route?";
const PASSWORD = process.env.E2E_PASSWORD ?? "e2e-password";
const TICKET_ID = "ab12cd34-0000-4000-8000-000000000001";
const PROPOSAL = {
  token: "tok-e2e", text: SENTENCE, category: "Transportation", priority: "low", office: "transport", action_kind: "ticket",
  question: null, faq: null, hint: null,
  why: { category: { label: "Transportation", prob: 0.93, set: ["Transportation"] }, priority: { label: "low", prob: 0.8, set: ["low"], evidence: [] }, neighbors: [] },
};

test("a student signs in, asks about the bus timetable and gets a Transportation answer", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);

  // The demo chip fills only the username; the student button signs in.
  await page.getByRole("button", { name: "talal", exact: true }).click();
  await expect(page.getByLabel("Username")).toHaveValue("talal");
  await expect(page.getByLabel("Password")).toHaveValue("");
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Log in as student" }).click();

  // Home, with the student tabs; the Ask tab opens the chat.
  await expect(page).toHaveURL(/localhost:\d+\/$/);
  await expect(page.getByRole("heading", { level: 1, name: "Announcements" })).toBeVisible();
  const nav = page.getByRole("navigation", { name: "Main menu" });
  await expect(nav.getByRole("link", { name: "Home" })).toHaveAttribute("aria-current", "page");
  await nav.getByRole("link", { name: "Ask" }).click();
  await expect(page).toHaveURL(/\/ask$/);
  await expect(page.getByRole("heading", { level: 1, name: "Ask CampusPulse" })).toBeVisible();

  // The chat routes are stubbed in the browser with the real response shapes (types.gen.ts), so the proposal token is fixed.
  await page.route("**/api/ai/chat/turn", (route) =>
    route.fulfill({ json: { mode: "agent", reply: "I can send this to Transport.", proposal: PROPOSAL, ticket_id: null, triage: null, clear_proposal: false } }),
  );
  let confirmed: unknown = null;
  await page.route("**/api/ai/chat/confirm", async (route) => {
    confirmed = route.request().postDataJSON();
    await route.fulfill({ json: { triage: { request_id: "r-1", status: "decided", flags: [], explanation: null, message: null }, ticket_id: TICKET_ID, hint_applied: false } });
  });

  await page.getByLabel("Your request").fill(SENTENCE);
  await page.getByRole("button", { name: "Send request" }).click();
  await expect(page.getByText(/no real department/)).toHaveCount(0);
  const proposal = page.getByRole("region", { name: "Suggested request" });
  await expect(proposal).toContainText("Department: Transport");
  await expect(proposal).not.toContainText("%");
  await proposal.getByRole("button", { name: "Yes, send it" }).click();
  expect(confirmed).toEqual({ proposal_token: "tok-e2e" });
  await expect(page.getByText("Request recorded #AB12CD34")).toBeVisible();
  await expect(page.getByRole("link", { name: "View this request" })).toHaveAttribute("href", `/requests/${TICKET_ID}`);

  // A student cannot open the staff pages: the proxy sends them back to "/".
  await page.goto("/admin");
  await expect(page).toHaveURL(/localhost:\d+\/$/);
});

test("the login buttons check the role: a student cannot log in as staff", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Username").fill("talal");
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Log in as staff" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "cannot log in" })).toContainText("cannot log in with that button");
  await expect(page).toHaveURL(/\/login$/);
});

test("when the assistant is unavailable the ask page shows the plain form", async ({ page }) => {
  await signInAs(page, "student");
  await expect(page).toHaveURL(/localhost:\d+\/$/);
  await page.goto("/ask");
  await page.route("**/api/ai/chat/turn", (route) => route.fulfill({ json: { mode: "fallback", reply: "", proposal: null, ticket_id: null, triage: null, clear_proposal: false } }));
  await page.route("**/api/ai/chat/preview", (route) => route.fulfill({ json: PROPOSAL }));
  await page.getByLabel("Your request").fill(SENTENCE);
  await page.getByRole("button", { name: "Send request" }).click();
  await page.getByRole("button", { name: "Check" }).click();
  await expect(page.getByRole("region", { name: "Suggested request" })).toContainText("Department: Transport");
});

const OLD_TICKET = {
  ticket_id: "ab12cd34-0000-4000-8000-000000000009", number: "AB12CD34", title: "Printer broken in H302", office: "facilities",
  category: "Facilities", priority: "medium", status: "new", awaiting_student: true, created_at: "2026-11-01T10:00:00Z", resolved_at: null,
};
const TURN = { mode: "agent", reply: "", proposal: null, ticket_id: null, triage: null, clear_proposal: false, tickets: [], correction: null, withdraw: null };

test("the chat box is the plain one: no microphone, no demo footer, Enter sends, and status and correction cards work", async ({ page }) => {
  await signInAs(page, "student");
  await page.goto("/ask");
  await expect(page.getByRole("heading", { level: 1, name: "Ask CampusPulse" })).toBeVisible();
  await expect(page.getByRole("button", { name: /dictate|microphone/i })).toHaveCount(0);
  await expect(page.locator("[data-footer]")).toHaveCount(0);
  const box = page.getByLabel("Your request");
  await expect(box).toHaveAttribute("placeholder", "Message CampusPulse…");
  await expect(page.getByRole("button", { name: "Send request" })).toBeDisabled();

  // Status turn: one card with the status word and a link to the request.
  await page.route("**/api/ai/chat/turn", (route) => {
    const body = route.request().postDataJSON() as { messages: { content: string }[] };
    const last = body.messages.at(-1)?.content ?? "";
    if (last.startsWith("status")) return route.fulfill({ json: { ...TURN, reply: "You have one open request.", tickets: [OLD_TICKET] } });
    return route.fulfill({ json: { ...TURN, reply: "Did you mean to fix #AB12CD34?", correction: { ticket: OLD_TICKET, old_text: "The printer in H302 is broken." }, proposal: { ...PROPOSAL, token: "tok-fix", text: "The printer in H203 is broken.", category: "Facilities", office: "facilities" } } });
  });
  await box.fill("status of my requests");
  await box.press("Enter");
  const card = page.getByRole("article");
  await expect(card).toHaveAttribute("data-status", "new");
  await expect(card).toContainText("Received");
  await expect(card).toContainText("The office replied, please check");
  await expect(card.getByRole("link", { name: "Open request #AB12CD34" })).toHaveAttribute("href", `/requests/${OLD_TICKET.ticket_id}`);

  // Correction turn: replace sends replace true and shows the old request as Closed.
  let confirmed: unknown = null;
  await page.route("**/api/ai/chat/confirm", async (route) => {
    confirmed = route.request().postDataJSON();
    await route.fulfill({ json: { triage: { request_id: "r-1", status: "decided", flags: [], explanation: null, message: null }, ticket_id: TICKET_ID, hint_applied: false, closed_ticket: { ...OLD_TICKET, status: "closed", awaiting_student: false } } });
  });
  await box.fill("I wrote H302, it is H203");
  await box.press("Enter");
  await expect(page.getByRole("heading", { name: "Fix request #AB12CD34?" })).toBeVisible();
  await page.getByRole("button", { name: "Yes, replace #AB12CD34" }).click();
  await expect(page.getByText("Request recorded #AB12CD34")).toBeVisible();
  expect(confirmed).toEqual({ proposal_token: "tok-fix", replace: true });
  await expect(page.locator('article[data-status="closed"]')).toContainText("Closed");
});
