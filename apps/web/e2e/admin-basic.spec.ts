import { expect, test, type Page } from "@playwright/test";

// P5.12 (model lab) and P5.15 (outbox) acceptance. Runs against the mock AI API (the metrics and
// red-team fixtures) and the fake Supabase (outbox rows, one for each status that matters).
const PASSWORD = process.env.E2E_PASSWORD ?? "e2e-password";

async function signInAs(page: Page, button: string) {
  await page.goto("/login");
  await page.getByRole("button", { name: button }).click();
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
}

const noHorizontalOverflow = (page: Page) =>
  page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth);

test("the admin lands on the model lab, reads the benchmark and runs the red team", async ({ page }) => {
  await signInAs(page, "Sign in as Admin");
  await expect(page).toHaveURL(/\/lab$/);
  await expect(page.getByRole("heading", { level: 1, name: "Model lab" })).toBeVisible();

  // Benchmark: a row per model (the fixture has six for category), every number with its counts.
  const category = page.getByRole("table", { name: /Category benchmark/ });
  await expect(category).toBeVisible();
  expect(await category.locator("tbody tr").count()).toBeGreaterThanOrEqual(5);
  await expect(category.getByText("432 rows, 30 groups").first()).toBeVisible();
  await expect(page.getByText("Model artifact v1 (3f9a2c71)")).toBeVisible();
  await expect(page.getByText(/no separate rows for set 1, set 2 and set 3/)).toBeVisible();

  // Calibration and fairness.
  await page.getByRole("tab", { name: "Calibration and fairness" }).click();
  await expect(page.getByRole("table", { name: /Category coverage/ })).toBeVisible();
  await expect(page.getByRole("table", { name: /macro-F1 per language/ })).toBeVisible();

  // Live system.
  await page.getByRole("tab", { name: "Live system" }).click();
  await expect(page.getByRole("table", { name: "Requests by tier" })).toContainText("Tier 0, offline models");

  // Red team: the metrics already list one scorecard. Run 20 attacks and the scorecard shows (the mock API
  // answers with the same run id, so the history merges it into that one card instead of adding a second).
  await page.getByRole("tab", { name: "Red team" }).click();
  const card = page.getByTestId("scorecard");
  await expect(card).toHaveCount(1);
  await page.getByRole("button", { name: "Run red team" }).click();
  await expect(page.getByText("Red team finished: 85% passed.")).toBeVisible();
  await expect(card).toHaveCount(1);
  await expect(card).toContainText("Passed: 85%");
  await card.getByText("3 failures", { exact: false }).last().click();
  await expect(card.getByRole("table", { name: /Failures of run/ })).toContainText("el printer bil lab 5arban mn embare7");
});

test("the model lab works in Arabic and right to left, with no sideways scroll on a phone", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signInAs(page, "Sign in as Admin");
  await expect(page).toHaveURL(/\/lab$/);
  await page.getByRole("button", { name: /العربية/ }).click();
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.getByRole("heading", { level: 1, name: "مختبر النماذج" })).toBeVisible();
  await expect(page.getByRole("table", { name: /مقارنة التصنيف/ })).toBeVisible();
  expect(await noHorizontalOverflow(page)).toBe(true);
  for (const tab of ["المعايرة والإنصاف", "النظام الحي", "الفريق الأحمر"]) {
    await page.getByRole("tab", { name: tab }).click();
    expect(await noHorizontalOverflow(page)).toBe(true);
  }
});

test("staff cannot open the model lab; students cannot open the lab or the outbox", async ({ page }) => {
  await signInAs(page, "Sign in as IT staff");
  await expect(page).toHaveURL(/\/staff$/);
  await page.goto("/lab");
  await expect(page).toHaveURL(/\/staff$/);
  // The staff navigation offers no model lab link.
  await expect(page.getByRole("navigation", { name: "Staff pages" }).getByRole("link", { name: "Model lab" })).toHaveCount(0);
  await page.context().clearCookies();

  await signInAs(page, "Sign in as Student");
  await expect(page).toHaveURL(/localhost:\d+\/$/);
  await page.goto("/lab");
  await expect(page).toHaveURL(/localhost:\d+\/$/);
  await page.goto("/outbox");
  await expect(page).toHaveURL(/localhost:\d+\/$/);
});

test("staff read the outbox, filter it by status and see why a message was rejected", async ({ page }) => {
  await signInAs(page, "Sign in as IT staff");
  await page.getByRole("navigation", { name: "Staff pages" }).getByRole("link", { name: "Outbox" }).click();
  await expect(page).toHaveURL(/\/outbox$/);
  await expect(page.getByRole("heading", { level: 1, name: "Outbox" })).toBeVisible();
  await expect(page.getByText("Demo accounts only")).toBeVisible();

  const table = page.getByRole("table", { name: "Outbox messages, newest first" });
  await expect(table.locator("tbody tr")).toHaveCount(5);
  await expect(table.getByText("SIMULATED", { exact: true })).toBeVisible();
  await expect(table.getByText("REJECTED", { exact: true })).toBeVisible();
  await expect(table.getByText("Deferred", { exact: true })).toBeVisible();
  await expect(table.getByText("Failed", { exact: true })).toBeVisible();
  await expect(table.getByText("Sent", { exact: true })).toBeVisible();

  await page.getByRole("radio", { name: "REJECTED (1)" }).click();
  await expect(table.locator("tbody tr")).toHaveCount(1);
  await expect(table).toContainText("someone@real.example");
  await expect(table).toContainText("recipient is not on the demo allow-list");

  await page.getByRole("radio", { name: "Queued (0)" }).click();
  await expect(page.getByText("No messages with this status")).toBeVisible();
  await page.getByRole("button", { name: "All (5)" }).click();
  await expect(table.locator("tbody tr")).toHaveCount(5);
});

test("the admin moves between lab, outbox, staff desk and pulse with the navigation", async ({ page }) => {
  await signInAs(page, "Sign in as Admin");
  await expect(page).toHaveURL(/\/lab$/);
  const nav = () => page.getByRole("navigation", { name: "Staff pages" });
  await expect(nav().getByRole("link", { name: "Model lab" })).toHaveAttribute("aria-current", "page");

  await nav().getByRole("link", { name: "Outbox" }).click();
  await expect(page).toHaveURL(/\/outbox$/);
  await expect(nav().getByRole("link", { name: "Outbox" })).toHaveAttribute("aria-current", "page");

  await nav().getByRole("link", { name: "Staff desk" }).click();
  await expect(page).toHaveURL(/\/staff$/);
  await expect(page.getByRole("heading", { level: 1, name: "Staff desk" })).toBeVisible();

  await nav().getByRole("link", { name: "Pulse map" }).click();
  await expect(page).toHaveURL(/\/pulse$/);
  await expect(page.getByRole("heading", { level: 1, name: "Campus Pulse" })).toBeVisible();

  await nav().getByRole("link", { name: "Model lab" }).click();
  await expect(page).toHaveURL(/\/lab$/);
});

test("the outbox works in Arabic and right to left with no sideways scroll on a phone", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signInAs(page, "Sign in as IT staff");
  await page.goto("/outbox");
  await page.getByRole("button", { name: /العربية/ }).click();
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.getByRole("heading", { level: 1, name: "صندوق الرسائل الصادرة" })).toBeVisible();
  await expect(page.getByText("حسابات تجريبية فقط")).toBeVisible();
  await expect(page.getByRole("table")).toContainText("مرفوضة");
  expect(await noHorizontalOverflow(page)).toBe(true);
});
