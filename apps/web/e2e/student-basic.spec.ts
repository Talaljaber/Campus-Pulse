import { expect, test } from "@playwright/test";

// P5.8 acceptance. Runs against the mock AI API and the fake Supabase from playwright.config.ts.
// The mock picks its fixture by the exact request text, so the full fixture sentence is typed.
const SENTENCE = "where is the bus timetable for the Madaba route?";
const PASSWORD = process.env.E2E_PASSWORD ?? "e2e-password";

test("a student signs in, asks about the bus timetable and gets a Transportation answer", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);

  // The demo button fills only the email.
  await page.getByRole("button", { name: "Sign in as Student" }).click();
  await expect(page.getByLabel("Email")).toHaveValue("talal@demo.local");
  await expect(page.getByLabel("Password")).toHaveValue("");
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();

  await expect(page).toHaveURL(/localhost:\d+\/$/);
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
