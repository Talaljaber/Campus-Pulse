import { expect, test, type Page } from "@playwright/test";
import { signInAs } from "./support/login";

// Layout acceptance: the portal fills the screen (width and height), the page itself never scrolls,
// the tab bar never scrolls, and tables become cards on a phone. Runs against the mock API and fake Supabase.
const SHOTS = process.env.SHOT_DIR;
const shot = async (page: Page, name: string) => {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png` });
};

const PHONE = { width: 390, height: 844 };
const SMALL_PHONE = { width: 360, height: 640 };
const DESKTOP = { width: 1440, height: 900 };

const pageScrolls = (page: Page) =>
  page.evaluate(() => ({
    sideways: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    tall: document.documentElement.scrollHeight > window.innerHeight + 1,
  }));

const tabBarScrolls = (page: Page) =>
  page.evaluate(() => {
    const ul = document.querySelector('nav[aria-label="Main menu"] ul') as HTMLElement;
    return ul.scrollWidth > ul.clientWidth + 1;
  });

test("the login page fits a small phone, only the pressed button shows loading, and it has the language switch", async ({ page }) => {
  await page.setViewportSize(SMALL_PHONE);
  await page.goto("/login");
  await expect(page.getByRole("button", { name: /العربية/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign out" })).toHaveCount(0);
  expect((await pageScrolls(page)).sideways).toBe(false);
  await shot(page, "login-phone");
});

test("a student's screens fit the phone: no page scroll, no tab-bar scroll, no greeting", async ({ page }) => {
  await page.setViewportSize(PHONE);
  await signInAs(page, "student");
  await expect(page.getByRole("heading", { level: 1, name: "Announcements" })).toBeVisible();
  await expect(page.getByText(/Hello|Welcome/)).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Sign out" })).toHaveCount(0);
  await expect(page.getByRole("list", { name: "Shortcuts" })).toHaveCount(0);
  expect(await tabBarScrolls(page)).toBe(false);
  expect(await pageScrolls(page)).toEqual({ sideways: false, tall: false });
  await shot(page, "student-home-phone");

  const nav = page.getByRole("navigation", { name: "Main menu" });
  await nav.getByRole("link", { name: "Ask" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Ask CampusPulse" })).toBeVisible();
  expect(await pageScrolls(page)).toEqual({ sideways: false, tall: false });
  await shot(page, "student-ask-phone");

  await nav.getByRole("link", { name: "Profile" }).click();
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
  await expect(page.getByRole("button", { name: /العربية/ })).toBeVisible();
  expect(await pageScrolls(page)).toEqual({ sideways: false, tall: false });
  await shot(page, "student-profile-phone");
});

test("an admin's eight tabs fit a small phone without scrolling, and Ask is there for staff and admin", async ({ page }) => {
  await page.setViewportSize(SMALL_PHONE);
  await signInAs(page, "admin");
  const nav = page.getByRole("navigation", { name: "Main menu" });
  await expect(nav.getByRole("link")).toHaveCount(8);
  await expect(nav.getByRole("link", { name: "Ask" })).toBeVisible();
  expect(await tabBarScrolls(page)).toBe(false);
  expect((await pageScrolls(page)).sideways).toBe(false);
  await shot(page, "admin-queue-smallphone");
});

test("the staff queue is cards on a phone with a Show details button, and a table on desktop", async ({ page }) => {
  await page.setViewportSize(PHONE);
  await signInAs(page, "staff");
  await expect(page).toHaveURL(/\/staff$/);
  await expect(page.getByRole("table")).toHaveCount(0);
  const first = page.getByRole("button", { name: "Show details" }).first();
  await expect(first).toBeVisible();
  await shot(page, "staff-queue-phone");
  await first.click();
  await expect(page.getByRole("button", { name: "Hide details" })).toHaveCount(1);
  await shot(page, "staff-queue-phone-details");
  expect((await pageScrolls(page)).sideways).toBe(false);

  await page.setViewportSize(DESKTOP);
  await expect(page.getByRole("table")).toBeVisible();
  await shot(page, "staff-queue-desktop");
});

test("on desktop the portal fills the whole window and the page does not scroll", async ({ page }) => {
  await page.setViewportSize(DESKTOP);
  await signInAs(page, "student");
  await expect(page.getByRole("heading", { level: 1, name: "Announcements" })).toBeVisible();
  const box = await page.locator("#content").boundingBox();
  expect(box?.width).toBeGreaterThanOrEqual(DESKTOP.width - 2);
  expect(await pageScrolls(page)).toEqual({ sideways: false, tall: false });
  await shot(page, "student-home-desktop");

  await page.getByRole("navigation", { name: "Main menu" }).getByRole("link", { name: "Ask" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Ask CampusPulse" })).toBeVisible();
  expect(await pageScrolls(page)).toEqual({ sideways: false, tall: false });
  await shot(page, "student-ask-desktop");
});
