# P10 package C — profile notification email UI

Implemented `NotificationEmailPanel` on the profile page and a typed browser service for `GET`, `PUT`, and `DELETE /v1/profile/email`. The field starts with the current saved address; consent starts unchecked and resets whenever the address changes or a save/remove succeeds. Save requires the explicit checkbox. Remove remains available when `opt_in_enabled=false`. The panel explains the shared demo account behavior, handles service failures and has English and Arabic copy.

Files: `apps/web/src/components/profile/NotificationEmailPanel.tsx`, `ProfileScreen.tsx`, `apps/web/src/lib/profiles/email.ts`, and the existing profile component tests in `apps/web/src/components/announcements/__tests__/announcements.test.tsx`.

Backend contract assumed from architecture: `{email: string|null, consented_at: string|null, opt_in_enabled: boolean}` for all three operations. `PUT` sends `{email, consent: true}`. Package A was informed of this shape.

Shared integration request: `apps/web/src/lib/ai/browser.ts` must permit `PUT`/`DELETE` (integrator added this during package C); `apps/web/src/lib/ai/allowlist.ts` must admit `GET`, `PUT`, `DELETE` for `profile/email`, and the proxy method type must permit them. No central i18n keys are required because the new component carries local bilingual copy; the integrator may consolidate it into the dictionaries later. Do not regenerate OpenAPI types until backend API is merged.

Checks run: focused vitest `17 passed`; web `typecheck` exit 0 after integrator extended the browser method union. No live API or SMTP call was made.

Limitations: frontend validation relies on the browser email input and server validation; the server is authoritative. GET failure shows an error and does not show save/remove controls. UI has not been exercised against the new live backend or a deployed profile.
