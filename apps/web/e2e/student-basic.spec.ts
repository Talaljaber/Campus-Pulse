import { expect, test } from "@playwright/test";

// P5.8 acceptance. Runs against the mock AI API and the fake Supabase from playwright.config.ts.
// The mock picks its fixture by the exact request text, so the full fixture sentence is typed.
const SENTENCE = "where is the bus timetable for the Madaba route?";
const PASSWORD = process.env.E2E_PASSWORD ?? "e2e-password";
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

  await page.getByLabel("Your request").fill(SENTENCE);
  await page.getByRole("button", { name: "Send request" }).click();

  const card = page.getByRole("article");
  await expect(card).toBeVisible();
  await expect(card).toContainText("Transportation");
  await expect(card).toContainText("Bus timetables for every route");
  await expect(page.getByText(/Integration-ready prototype on synthetic data/)).toBeVisible();

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
