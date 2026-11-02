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
const DEMO_LINE = "Demo: simulated portal, not the official university system. No real department is contacted.";

test("a student signs in, asks about the bus timetable and gets a Transportation answer", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);

  // The demo line is in the footer of the login page too.
  await expect(page.getByText(DEMO_LINE).first()).toBeVisible();

  // The demo chip fills only the username; the student button signs in.
  await page.getByRole("button", { name: "talal", exact: true }).click();
  await expect(page.getByLabel("Username")).toHaveValue("talal");
  await expect(page.getByLabel("Password")).toHaveValue("");
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Log in as student" }).click();

  // Home, with the student tabs; the Ask tab opens the chat.
  await expect(page).toHaveURL(/localhost:\d+\/$/);
  await expect(page.getByRole("heading", { level: 1, name: "Welcome, talal" })).toBeVisible();
  await expect(page.getByText(DEMO_LINE).first()).toBeVisible();
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
  await expect(page.getByText("Demo: no real department is contacted.")).toBeVisible();
  const proposal = page.getByRole("region", { name: "Suggested request" });
  await expect(proposal).toContainText("Department: Transport");
  await expect(proposal).not.toContainText("%");
  await proposal.getByRole("button", { name: "Yes, send it" }).click();
  expect(confirmed).toEqual({ proposal_token: "tok-e2e" });
  await expect(page.getByText("Request recorded #AB12CD34")).toBeVisible();
  await expect(page.getByRole("link", { name: "View this request" })).toHaveAttribute("href", `/requests/${TICKET_ID}`);

  // A student cannot open the staff pages: the proxy sends them back to "/".
  await page.goto("/lab");
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
