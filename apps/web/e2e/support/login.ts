import type { Page } from "@playwright/test";

const PASSWORD = process.env.E2E_PASSWORD ?? "e2e-password";

/** The demo usernames the e2e specs use: the fake Supabase knows them as `<username>@demo.local`. */
const WHO = {
  student: { username: "talal", button: "Log in as student" },
  staff: { username: "it", button: "Log in as staff" },
  admin: { username: "admin", button: "Log in as staff" },
} as const;

/** Logs in through the portal login card: demo chip fills the username, the password is typed, the role button is pressed. */
export async function signInAs(page: Page, who: keyof typeof WHO): Promise<void> {
  const { username, button } = WHO[who];
  await page.goto("/login");
  await page.getByRole("button", { name: username, exact: true }).click();
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: button }).click();
}

/** Switches the portal to Arabic through the language switch on the Profile page (it is no longer in the header); the choice is kept in a cookie. */
export async function switchToArabic(page: Page): Promise<void> {
  await page.goto("/profile");
  await page.getByRole("button", { name: /العربية/ }).click();
}
