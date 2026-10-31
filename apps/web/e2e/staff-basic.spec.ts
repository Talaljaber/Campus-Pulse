import { expect, test, type Page } from "@playwright/test";

// P5.10 acceptance. Runs against the mock AI API and the fake Supabase (which stands in for row-level
// security on tickets: the IT staff login only gets IT tickets). Realtime is not faked.
const PASSWORD = process.env.E2E_PASSWORD ?? "e2e-password";

async function signInAs(page: Page, button: string) {
  await page.goto("/login");
  await page.getByRole("button", { name: button }).click();
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
}

test("staff see their office queue, open a request, correct a review item and resolve an incident", async ({ page }) => {
  await signInAs(page, "Sign in as IT staff");
  await expect(page).toHaveURL(/\/staff$/);
  await expect(page.getByRole("heading", { level: 1, name: "Staff desk" })).toBeVisible();
  await expect(page.getByText("Office: IT Support")).toBeVisible();

  // Queue: only the IT office, the overdue ticket is marked, the finished one is hidden by the default filter.
  const queue = page.getByRole("list", { name: "Ticket queue" });
  await expect(queue.getByRole("article")).toHaveCount(1);
  await expect(queue).toContainText("Wi-Fi is down in building M");
  await expect(queue).toContainText("Overdue by 3 h");
  await expect(queue).toContainText("Open CP-47 in Linear");
  await expect(page.getByText("Fee receipt missing")).toHaveCount(0);

  // Status change goes through the proxy to the (mock) API.
  await page.getByRole("combobox", { name: "Status of Wi-Fi is down in building M" }).selectOption("in_progress");
  await expect(page.getByText("Status changed to In progress.")).toBeVisible();

  // Request details with the collapsed explanation.
  await page.getByRole("button", { name: "Open details for Wi-Fi is down in building M" }).click();
  await expect(page.getByRole("region", { name: "What the student wrote" })).toContainText("the wifi in building M is down again");
  await expect(page.getByText("Dictated by voice")).toBeVisible();
  const details = page.locator("details", { hasText: "Why this result" });
  await expect(details).not.toHaveAttribute("open", "");
  await details.getByText("Why this result", { exact: true }).first().click();
  await expect(details).toHaveAttribute("open", "");

  // Review queue: correct once, see the memory toast, the item leaves.
  await page.getByRole("tab", { name: "Needs review (1)" }).click();
  await expect(page.getByRole("article")).toContainText("my account is on hold after paying fees");
  await expect(page.getByText("Category could be Finance / Registration.")).toBeVisible();
  await page.getByRole("button", { name: "Correct" }).click();
  await page.getByLabel("Category").selectOption("Registration");
  await page.getByRole("button", { name: "Save correction" }).click();
  await expect(page.getByText("Added to memory: it will influence similar requests right away.")).toBeVisible();
  await expect(page.getByRole("tab", { name: "Needs review (0)" })).toBeVisible();
  await expect(page.getByText("Nothing waits for review")).toBeVisible();

  // Incidents: resolving asks for confirmation first.
  await page.getByRole("tab", { name: "Incidents (1)" }).click();
  await expect(page.getByText("Wi-Fi outage in building M")).toBeVisible();
  await page.getByRole("button", { name: "Resolve", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Resolve incident" }).click();
  await expect(page.getByText(/Incident resolved\. 4 reporters notified\./)).toBeVisible();
  await expect(page.getByRole("tab", { name: "Incidents (0)" })).toBeVisible();
});

test("the staff page works in Arabic and right to left", async ({ page }) => {
  await signInAs(page, "Sign in as IT staff");
  await expect(page).toHaveURL(/\/staff$/);
  await page.getByRole("button", { name: /العربية/ }).click();
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.getByRole("heading", { level: 1, name: "مكتب الموظفين" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "التذاكر" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(overflow).toBe(false);
});

test("an admin sees every office", async ({ page }) => {
  await signInAs(page, "Sign in as Admin");
  await page.goto("/staff");
  await expect(page.getByText("All offices")).toBeVisible();
  await expect(page.getByRole("button", { name: "Open details for Fee receipt missing" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open details for Wi-Fi is down in building M" })).toBeVisible();
});
