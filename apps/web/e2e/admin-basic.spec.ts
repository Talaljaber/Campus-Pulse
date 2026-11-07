import { expect, test, type Page } from "@playwright/test";
import { signInAs, switchToArabic } from "./support/login";

// P10.17 (admin Overview) and P5.15 (outbox) acceptance. Runs against the mock AI API (the usage and
// health fixtures) and the fake Supabase (the overview function and outbox rows).

const noHorizontalOverflow = (page: Page) =>
  page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth);

test("the admin lands on the Overview: alerts, key numbers, offices, AI handling, cost and delivery", async ({ page }) => {
  await signInAs(page, "admin");
  await expect(page).toHaveURL(/\/admin$/);
  await expect(page.getByRole("heading", { level: 1, name: "Overview" })).toBeVisible();
  const nav = page.getByRole("navigation", { name: "Main menu" });
  await expect(nav.getByRole("link", { name: "Overview" })).toHaveAttribute("aria-current", "page");
  await expect(nav.getByRole("link", { name: "Reports" })).toHaveCount(0);

  const alerts = page.getByRole("region", { name: "Needs attention" });
  await expect(alerts).toContainText("1 high-priority tickets are still open.");
  await expect(alerts).toContainText("10 open tickets are past their response time.");
  await expect(page.getByRole("region", { name: "Key numbers" })).toContainText("12 min");
  await expect(page.getByRole("table", { name: "Backlog and response times per office" }).locator("tbody tr")).toHaveCount(6);
  await expect(page.getByRole("region", { name: "How the assistant handled requests" })).toContainText("76%");
  await expect(page.getByRole("region", { name: "AI cost" })).toContainText("$3.33");
  await expect(page.getByRole("region", { name: "Delivery and service" })).toContainText("Online");

  // The period picker reloads the numbers for another window.
  await page.getByRole("combobox", { name: "Period" }).selectOption("7");
  await expect(page).toHaveURL(/\/admin\?days=7$/);
  await expect(page.getByRole("img", { name: /in the last 7 days/ })).toBeVisible();

  // The model lab is gone.
  await page.goto("/lab");
  await expect(page.getByRole("heading", { level: 1, name: "Model lab" })).toHaveCount(0);
});

test("the Overview works in Arabic and right to left, with no sideways scroll on a phone", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signInAs(page, "admin");
  await switchToArabic(page);
  await page.goto("/admin");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.getByRole("heading", { level: 1, name: "نظرة عامة" })).toBeVisible();
  await expect(page.getByRole("region", { name: "بحاجة إلى انتباه" })).toBeVisible();
  expect(await noHorizontalOverflow(page)).toBe(true);
});

test("staff cannot open the Overview or Accounts; students cannot open them or the outbox", async ({ page }) => {
  await signInAs(page, "staff");
  await expect(page).toHaveURL(/\/staff$/);
  await page.goto("/admin");
  await expect(page).toHaveURL(/\/staff$/);
  const nav = page.getByRole("navigation", { name: "Main menu" });
  await expect(nav.getByRole("link", { name: "Overview" })).toHaveCount(0);
  await expect(nav.getByRole("link", { name: "Accounts" })).toHaveCount(0);
  await page.goto("/admin/accounts");
  await expect(page).toHaveURL(/\/staff$/);
  await page.context().clearCookies();

  await signInAs(page, "student");
  await expect(page).toHaveURL(/localhost:\d+\/$/);
  await page.goto("/admin");
  await expect(page).toHaveURL(/localhost:\d+\/$/);
  await page.goto("/outbox");
  await expect(page).toHaveURL(/localhost:\d+\/$/);
});

test("staff read the outbox, filter it by status and see why a message was rejected", async ({ page }) => {
  await signInAs(page, "staff");
  await page.goto("/outbox");
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

test("the admin moves between the Overview, queue, incidents, accounts and the outbox shortcut on Profile", async ({ page }) => {
  await signInAs(page, "admin");
  await expect(page).toHaveURL(/\/admin$/);
  const nav = () => page.getByRole("navigation", { name: "Main menu" });
  await expect(nav().getByRole("link", { name: "Overview" })).toHaveAttribute("aria-current", "page");

  await page.getByRole("link", { name: "Profile" }).click();
  await expect(page).toHaveURL(/\/profile$/);
  await page.getByRole("link", { name: "Outbox" }).click();
  await expect(page).toHaveURL(/\/outbox$/);
  await expect(page.getByRole("heading", { level: 1, name: "Outbox" })).toBeVisible();

  await nav().getByRole("link", { name: "Incidents" }).click();
  await expect(page).toHaveURL(/\/pulse$/);
  await expect(page.getByRole("heading", { level: 1, name: "Campus Pulse" })).toBeVisible();

  await nav().getByRole("link", { name: "Accounts" }).click();
  await expect(page).toHaveURL(/\/admin\/accounts$/);
  await expect(page.getByRole("table", { name: "Accounts" })).toBeVisible();

  await nav().getByRole("link", { name: "Queue" }).click();
  await expect(page).toHaveURL(/\/staff$/);
  await expect(page.getByRole("heading", { level: 1, name: "Staff desk" })).toBeVisible();

  await nav().getByRole("link", { name: "Overview" }).click();
  await expect(page).toHaveURL(/\/admin$/);
});

test("the outbox works in Arabic and right to left with no sideways scroll on a phone", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signInAs(page, "staff");
  await switchToArabic(page);
  await page.goto("/outbox");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.getByRole("heading", { level: 1, name: "صندوق الرسائل الصادرة" })).toBeVisible();
  await expect(page.getByText("حسابات تجريبية فقط")).toBeVisible();
  await expect(page.getByRole("table")).toContainText("مرفوضة");
  expect(await noHorizontalOverflow(page)).toBe(true);
});
