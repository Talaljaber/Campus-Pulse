# P10 package A report — notification email persistence and API

Implemented in the shared workspace on 2026-11-03. SQL has not been applied. No external email was sent.

## Deliverables

- `supabase/migrations/0016_notify_email.sql`: nullable address/consent timestamp pair; authenticated SELECT restricted to the previous profile columns; service-only change ledger and atomic row-locked save/remove RPCs. The sixth accepted change within a rolling hour returns `limited`; identical saved address returns `unchanged` without consuming the limit. The two FK indexes mentioned in the original sketch already exist in 0015 and are not duplicated.
- `application/use_cases/profile_email.py`: typed store contract, conservative single-address normalization, consent and disabled-switch service logic.
- `adapters/store/profile_email_supabase.py`: service-role PostgREST adapter, including a live consent lookup.
- `frameworks/routes/profile_email.py`: GET/PUT/DELETE endpoints. Integration must register `profile_email_get`, `profile_email_put`, `profile_email_delete` operation IDs and wire `ApiServices.profile_email`.
- `tests/unit/test_profile_email_p10.py`: validation, consent, disabled switch and removal checks.

## Integration contract

`SupabaseProfileEmailStore(client)` implements `get(profile_id)`, `set_with_limit(profile_id,email,now,limit=5,window_s=3600)`, `remove(profile_id)`, and `has_active_consent(email)`. Construct `ProfileEmailService(store, opt_in_enabled=settings.email_opt_in)` and inject it as `services.profile_email`. The mail policy can call the store consent lookup at send time. Endpoint response is `{email, consented_at, opt_in_enabled}`.

The shared DTO and API registry belong to the integrator. The route currently declares the body/response models locally; move them to `application/dto.py` before adding the registry docs, and update the route imports. The rate-limit path currently uses HTTP 429 with the existing generic `invalid_input` error code because `ErrorCode` has no rate-limit member. The integrator may add a dedicated code to preserve the project-wide error contract.

## Checks and limitations

`ruff check` and strict mypy passed on the three new Python modules. Focused pytest: 7 passed. `git diff --check` passed. The SQL RPC concurrency and profile column grants require a live Supabase test after migration application; no local Postgres validation was run. Route import and OpenAPI generation depend on the integrator adding the three operation IDs.
