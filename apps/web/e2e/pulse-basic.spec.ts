import { expect, test } from "@playwright/test";
import { signInAs } from "./support/login";

// P5.11 acceptance (the snapshot half). The fake Supabase does not speak Realtime, so live inserts
// and bumps are covered by the reducer and hook unit tests; this checks the real page, the real
// proxy and the mock API end to end: map, dots, ring, feed, building filter, resolve, RTL, guard.

test("staff see dots, an incident ring and the feed, filter by building and resolve the incident", async ({ page }) => {
  await signInAs(page, "staff");
  await expect(page).toHaveURL(/\/staff$/);
  await page.goto("/pulse");
  await expect(page.getByRole("heading", { level: 1, name: "Campus Pulse" })).toBeVisible();

  // Map: a dot for each located request, a ring with the report count for the open incident.
  const map = page.getByRole("group", { name: "Campus map" });
  await expect(map.getByRole("img", { name: "IT Support, High priority request" })).toBeVisible();
  await expect(map.getByRole("img", { name: "Facilities, Medium priority request (simulated)" })).toBeVisible();
  await expect(map.getByRole("img", { name: "Incident with 4 reports, High priority" })).toBeVisible();

  // Feed: sentences, with the SIMULATED badge on demo traffic.
  const feed = page.getByRole("log", { name: "Live feed" });
  await expect(feed).toContainText("Incident opened: Wi-Fi outage in building M");
  await expect(feed).toContainText("New IT Support request, High priority in building M");
  await expect(feed).toContainText("Message sent: Wi-Fi in building M: we are on it");
  await expect(feed.getByText("SIMULATED").first()).toBeVisible();

  // Choosing a building narrows the incident list; choosing it again clears it.
  await map.getByRole("button", { name: /Building A,/ }).click();
  await expect(page.getByText("No open incidents")).toBeVisible();
  await page.getByRole("button", { name: "Show all buildings" }).click();
  await expect(page.getByRole("list", { name: "Open incidents" })).toContainText("Wi-Fi outage in building M");

  // Resolve asks first, then calls the API, then the ring and the list go.
  await page.getByRole("button", { name: "Resolve", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Resolve incident" }).click();
  await expect(page.getByText(/Incident resolved\. 4 reporters notified\./)).toBeVisible();
  await expect(map.getByRole("img", { name: /Incident with/ })).toHaveCount(0);
  await expect(feed).toContainText("Incident resolved: Wi-Fi outage in building M");
});

test("the pulse page works in Arabic and right to left, and the map keeps its geometry", async ({ page }) => {
  await signInAs(page, "staff");
  await page.goto("/pulse");
  await page.getByRole("button", { name: /العربية/ }).click();
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.getByRole("heading", { level: 1, name: "نبض الجامعة" })).toBeVisible();
  await expect(page.getByRole("log", { name: "الأحداث المباشرة" })).toBeVisible();
  await expect(page.locator("svg[dir=ltr]").first()).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(overflow).toBe(false);
});

test("a student cannot open the pulse page", async ({ page }) => {
  await signInAs(page, "student");
  await expect(page).toHaveURL(/localhost:\d+\/$/);
  await page.goto("/pulse");
  await expect(page).toHaveURL(/localhost:\d+\/$/);
});
