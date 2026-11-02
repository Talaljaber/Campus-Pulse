import { expect, test } from "@playwright/test";
import { signInAs } from "./support/login";

// P9.6 acceptance. Runs against the mock AI API and the fake Supabase (which stands in for row-level
// security on tickets: the IT staff login only gets IT tickets). Realtime is not faked. The comments
// endpoint is stubbed in the browser, because the mock API may not have it yet.

test("staff see their office queue as a table, hide their own request and open the workspace", async ({ page }) => {
  await signInAs(page, "staff");
  await expect(page).toHaveURL(/\/staff$/);
  await expect(page.getByRole("heading", { level: 1, name: "Staff desk" })).toBeVisible();
  await expect(page.getByText("Office: IT Support")).toBeVisible();

  // Queue: only the IT office, the overdue ticket carries a word and an icon, finished and own tickets are hidden.
  const table = page.getByRole("table", { name: "Ticket queue" });
  await expect(table.getByRole("row")).toHaveCount(2);
  const row = table.getByRole("row", { name: /Wi-Fi is down in building M/ });
  await expect(row).toContainText("Urgent");
  await expect(row).toContainText("Overdue");
  await expect(row).toContainText(/overdue by 3 h/);
  await expect(page.getByText("Fee receipt missing")).toHaveCount(0);
  await expect(page.getByText("Reset my e-learning password")).toHaveCount(0);
  await expect(page.getByText("My own laptop request")).toHaveCount(0);
  await expect(table.getByRole("columnheader", { name: "Office" })).toHaveCount(0);

  // The finished filter shows the solved ticket with a stopped clock.
  await page.locator("fieldset").getByLabel("Status").selectOption("done");
  await page.getByRole("button", { name: "Search" }).click();
  await expect(table.getByRole("row", { name: /Reset my e-learning password/ })).toContainText("Stopped");

  // Back to the active ones, open the workspace by clicking the row.
  await page.getByRole("button", { name: "Reset" }).click();
  await table.getByRole("row", { name: /Wi-Fi is down in building M/ }).click();
  await expect(page).toHaveURL(/\/staff\/tickets\/t-1$/);
  await expect(page.getByRole("heading", { level: 1, name: "Ticket T1" })).toBeVisible();
  await expect(page.getByText("the wifi in building M is down again").first()).toBeVisible();
  await expect(page.getByText("Dictated by voice")).toBeVisible();
  const details = page.locator("details", { hasText: "Why this result" });
  await expect(details).not.toHaveAttribute("open", "");
  await details.getByText("Why this result", { exact: true }).first().click();
  await expect(details).toHaveAttribute("open", "");

  // The thread marks the internal note in words.
  const thread = page.getByRole("list", { name: "Ticket history" });
  await expect(thread).toContainText("Ticket created");
  await expect(thread).toContainText("Internal note, not visible to the requester");
  await expect(thread).toContainText("Checked the switch in M, looks fine");

  // An internal note goes out with internal true; the answer joins the thread.
  let sent: unknown = null;
  await page.route("**/api/ai/tickets/t-1/comments", async (route) => {
    sent = route.request().postDataJSON();
    await route.fulfill({
      json: {
        ticket: {
          id: "t-1", request_id: "r-1", incident_id: null, office: "it", category: "IT Support", priority: "high", status: "new",
          provisional: false, sla_due_at: new Date(Date.now() - 3 * 3_600_000).toISOString(), escalated_at: null, resolved_at: null,
          title: "Wi-Fi is down in building M", links: [], clock_started_at: new Date().toISOString(), reminder_sent_at: null,
          awaiting_student: false, reminder_count: 0,
        },
        activity: {
          id: "ac-9", ticket_id: "t-1", kind: "note", visibility: "internal", actor_role: "staff", actor_alias: "staff-it", actor_office: "it",
          body: "Vendor called", from_status: null, to_status: null, from_office: null, to_office: null, from_priority: null, to_priority: null,
          created_at: new Date().toISOString(),
        },
      },
    });
  });
  await page.getByRole("radio", { name: "Internal note" }).check();
  await page.getByLabel("Your note").fill("Vendor called");
  await page.getByRole("button", { name: "Save note" }).click();
  await expect(page.getByText("Internal note saved.")).toBeVisible();
  await expect(thread).toContainText("Vendor called");
  expect(sent).toEqual({ body: "Vendor called", internal: true, status: null });

  // A staff member never opens their own ticket.
  await page.goto("/staff/tickets/t-4");
  await expect(page.getByText("This ticket does not exist, or you cannot open it.")).toBeVisible();
});

test("the corrections page lists the flagged requests and the past corrections", async ({ page }) => {
  await signInAs(page, "staff");
  await page.goto("/staff/reviews");
  await expect(page.getByRole("heading", { level: 3, name: "Past corrections" })).toBeVisible();
  const table = page.getByRole("table", { name: "Past corrections" });
  await expect(table).toContainText("my fee receipt is missing");
  await expect(table).toContainText("Forward");
  await expect(page.getByRole("heading", { level: 3, name: "Flagged requests" })).toBeVisible();
});

test("the staff page works in Arabic and right to left", async ({ page }) => {
  await signInAs(page, "staff");
  await expect(page).toHaveURL(/\/staff$/);
  await page.getByRole("button", { name: /العربية/ }).click();
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.getByRole("heading", { level: 1, name: "مكتب الموظفين" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: /رقم التذكرة/ })).toBeVisible();
  await expect(page.getByRole("table").getByText("عاجل").first()).toBeVisible();
  await expect(page.getByRole("table").getByText("متأخر").first()).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(overflow).toBe(false);

  await page.goto("/staff/tickets/t-1");
  await expect(page.getByRole("heading", { level: 1, name: /التذكرة/ })).toBeVisible();
  await expect(page.getByText("ملاحظة داخلية، ما بشوفها صاحب الطلب")).toBeVisible();
  const overflowWs = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(overflowWs).toBe(false);
});

test("an admin sees every office, with the office column", async ({ page }) => {
  await signInAs(page, "admin");
  await page.goto("/staff");
  await expect(page.getByText("All offices")).toBeVisible();
  const table = page.getByRole("table", { name: "Ticket queue" });
  await expect(table.getByRole("columnheader", { name: /Office/ })).toBeVisible();
  await expect(table.getByRole("row", { name: /Fee receipt missing/ })).toContainText("Finance");
  await expect(table.getByRole("row", { name: /Wi-Fi is down in building M/ })).toContainText("IT Support");
});
