import { expect, test } from "@playwright/test";

test("kitchen sink: both languages, every interactive element is reachable by Tab, no overflow", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/dev/ui");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

  // Both languages are on the page side by side, the Arabic one right-to-left.
  await expect(page.locator('div[lang="en"][dir="ltr"]')).toHaveCount(1);
  await expect(page.locator('div[lang="ar"][dir="rtl"]')).toHaveCount(1);

  // Tag every focusable element that should be a tab stop (roving tabindex = -1 excluded).
  const total = await page.evaluate(() => {
    const sel = 'a[href], button:not([disabled]), [tabindex]';
    const els = Array.from(document.querySelectorAll<HTMLElement>(sel)).filter((el) => {
      const r = el.getBoundingClientRect();
      // roving-tabindex members (tabindex=-1) are reached with arrow keys, not Tab
      return el.tabIndex >= 0 && r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== "hidden";
    });
    els.forEach((el, i) => el.setAttribute("data-ti", String(i)));
    return els.length;
  });
  expect(total).toBeGreaterThan(20);

  const seen = new Set<string>();
  for (let i = 0; i < total + 10; i++) {
    await page.keyboard.press("Tab");
    const ti = await page.evaluate(() => document.activeElement?.getAttribute("data-ti") ?? null);
    if (ti !== null) seen.add(ti);
  }
  const missing = Array.from({ length: total }, (_, i) => String(i)).filter((i) => !seen.has(i));
  expect(missing, "elements never reached by Tab").toEqual([]);

  // Narrow viewport: the page must not scroll sideways (RTL overflow regression guard).
  await page.setViewportSize({ width: 390, height: 800 });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);

  // Theme forcing works.
  await page.getByRole("radio", { name: "Dark" }).first().click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
});
