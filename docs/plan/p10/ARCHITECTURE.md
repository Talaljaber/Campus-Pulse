# P10 implementation architecture

Status: architecture prepared 2026-11-03 at the user's request. Implementation has not resumed. This document supplies the contracts and dispatch packages for smaller implementation agents. The original observations and user decisions remain in [PLAN.md](PLAN.md). Decisions below resolve implementation details; they do not authorize deployment, live emails, or applying SQL.

## 1. Scope and existing seams

Keep the frozen classifier, training data, model artifacts and offline prediction path untouched. P10 changes the online product. Use synthetic fixtures and existing permitted development tests; organizer-only files and evaluation results are outside every P10 package.

Verified source seams:

- `application/use_cases/chat.py`: preview is a proposal; confirmation calls `TriageUseCase.run(chat_confirmed=True)`. Signed tokens are currently claimed in process.
- `application/use_cases/triage.py`: stores embeddings and calls incident detection; currently returns before detection when location is absent. Both that guard and the detector need changing for optional location.
- `application/use_cases/incidents.py`: one incident ticket goes to Linear; every reporter retains a local `merged` ticket. Earlier individual issues are marked duplicate when the incident forms.
- `application/use_cases/ticket_emails.py`: `InboxBook` selects one requester/office address today. P10 needs multiple office recipients.
- `adapters/notify/allowlist.py` and `adapters/notify/gmail_smtp.py`: BOTH enforce recipient policy. Updating just the outer wrapper leaves consented emails blocked at SMTP.
- `application/use_cases/chat_ports.py`: context currently contains announcement strings and a pending proposal; it does not contain a general knowledge-base retrieval service. `ProposalFacts` contains an optional FAQ answer. Hints contain routing corrections, not verified operational advice.
- `adapters/llm/cached_chat.py`: exceptions become `None`; retry decisions must happen before this loss of error detail.
- Migration 0015 already creates `announcements_created_by_idx` and `ticket_hints_ticket_id_idx`. Do not recreate those in 0016.

Paths below are relative to `services/ai/campuspulse_ai/` unless they begin with another repository root directory.

## 2. Delivery gates and ownership

Each package gets a separate branch/worktree, a small commit and `docs/plan/p10/<package>_report.md`. Reports list changed contracts, commands actually run, results and limitations. Do not claim gates that were not run. No push or deployment in an implementation package.

| Package | Deliverable | Dependencies | Exclusive ownership |
|---|---|---|---|
| A | Notification persistence and API | none | 0016 SQL, new profile email domain/application/store/routes modules |
| B | Recipient policy and mail delivery | A contracts | notifier policy, SMTP wiring interface, ticket mail recipient resolution |
| C | Profile notification UI | A contracts | profile UI, profile types/repository/service, local UI tests |
| D | Grounded chat and scoped retry | none | chat adapter, chat ports, prompt v2, chat composition, new grounding/retry helpers |
| E | Shared-issue persistence and matching | A merged; contract gate below | 0017 SQL, incident detector, incident domain/store contracts, new shared-issue service |
| F | Confirm/join/separate request flow | D and E merged | chat use case, triage entry point, proposal tokens/DTO additions, incident actions, proposal UI |
| G | Announcement drafts and broadcasts | B, E and F merged | announcement use case/store/routes/UI, broadcast worker and templates |
| I | Integration | each wave | online composition, central settings, shared DTO/API registry, route registration, proxy allow-list, generated contracts/docs, shared localization files |

A and D may start together. B and C follow A's frozen interface. E begins after A merges; F and G are sequential. The integrator owns shared files: agents provide exact patches/interface requirements in their reports instead of concurrently editing these files. Package D can edit its own `composition/chat.py`; the integrator owns `composition/online.py`.

Before E implementation, its agent must document current incident membership storage, ticket-to-request relationships, RLS and vector search filters in its report, and map the schema additions below to them. Preserve existing membership storage when it supports the required uniqueness. Do not invent a second incident engine.

## 3. P10.1: notification email

### Data and API

Migration `0016_notify_email.sql` adds nullable `profiles.notify_email` and `profiles.notify_email_consent_at`; require both set or both null. Notification addresses are private profile data: own profile and service-role access only. Check existing table SELECT grants/RLS before adding columns; staff directory readers must not gain access to notification addresses. API writes derive profile ID from the authenticated actor, never from the body.

Add a service-only change ledger keyed by profile ID and timestamp. A database function locks the profile, counts accepted PUTs in the trailing hour, rejects the sixth, then writes email, server consent timestamp and ledger entry atomically. DELETE clears both fields immediately and is never blocked by the PUT limit. No plaintext address in the ledger. No direct authenticated writes to either column or ledger.

| Endpoint | Input | Success | Errors |
|---|---|---|---|
| `GET /v1/profile/email` | authenticated caller | `{email: string|null, consented_at: ISO|null, opt_in_enabled: boolean}` | 401 |
| `PUT /v1/profile/email` | `{email: string, consent: true}` | same shape | 401, 422 invalid/missing consent, 429 rate limit, 503 opt-in disabled |
| `DELETE /v1/profile/email` | authenticated caller | cleared shape | 401 |

Trim surrounding whitespace, reject CR/LF, display names, lists and malformed addresses. Use one normalization function for stored addresses, configured addresses, comparison and deduplication. Preserve the local part and lowercase the domain. Same normalized address plus existing consent is an idempotent PUT and consumes no change. No verification code, per the user decision.

### Policy and recipients

New application contracts (concrete names may follow existing naming conventions, behavior is fixed):

```
ProfileEmailStore.get(profile_id) -> NotificationEmail | None
ProfileEmailStore.set_with_limit(profile_id, email, now, limit=5, window_s=3600) -> NotificationEmail
ProfileEmailStore.remove(profile_id) -> None
ProfileEmailStore.has_active_consent(email) -> bool
RecipientResolver.requester(alias) -> tuple[str, ...]
RecipientResolver.office(office, exclude_alias) -> tuple[str, ...]
RecipientResolver.broadcast_audience() -> tuple[str, ...]
EmailRecipientPolicy.allows(address) -> bool
```

Policy: configured allow-list OR (`EMAIL_OPT_IN=true` AND current profile consent). A failed consent lookup denies the opt-in branch; a configured allow-listed address remains eligible. Default `EMAIL_OPT_IN=false`. This switch disables consent-based delivery and saves; existing configured demo delivery remains enabled. DELETE always works. Reuse the existing SMTP daily cap for the all-email cap.

Inject the SAME policy implementation into the outer notifier and SMTP; retain both enforcement points. Never broaden authorization for in-app notifications. Check consent at send time, including queued sends, so removal takes effect before delivery. Avoid indefinite positive consent caches.

Requester precedence: consented notification address, then existing explicitly configured demo fallback if policy allows it. Office audience: configured office inbox plus consented staff profiles whose current office matches. Exclude the requester's profile AND resolved requester addresses; deduplicate normalized addresses per event. A role of admin alone does not subscribe someone to every office. Never use fictional university_email or scraped addresses.

Adapt the lifecycle mail dispatch to iterate recipients; do not make one successful email mask another failure. Preserve event context and outbox failure logging. Replace SMTP's inaccurate developer-owned-inbox footer with wording covering consented demo recipients.

### UI and acceptance

Profile shows current notification address, unchecked consent for a new/changed value, Save and Remove. Show disabled-state explanation when opt-in is off. Do not pre-check consent or save when typing. Shared demo accounts use last saved address; explain this beside the field.

Tests use fake senders only: own-profile enforcement, invalid input/CRLF, sixth concurrent write rejected, idempotent save, removal despite limit, disabled opt-in, failed DB lookup, both policy gates, requester exclusion, office fan-out/deduplication, consent removed before queued send. Verify no real SMTP connection in the suite.

## 4. P10.2: grounded replies and retry

Add immutable `GroundingSource(id, kind, text, scope)` values to `ChatContext`, with a default empty collection for compatibility. Allowed kinds: announcement, FAQ and routing_hint. Construct them on the server from data retrieved for the current turn. The server creates IDs; the LLM cannot create sources. Keep existing announcement fields temporarily if required by existing tests, but generate both representations from the same data.

Announcements support operational facts only within their stated place/time scope. A FAQ supports only its answer. A routing hint supports a suggested office/category, never an ETA, workaround or claim that staff are working on a problem. Conversation history and previous assistant messages are not evidence. No new knowledge-base service is part of this package; a source not actually retrieved is unavailable.

Prompt v2 applies to BOTH `reply` and `phrase`. Ask for optional `source_ids` alongside existing JSON fields; extend `AgentReply` with a default empty tuple, leaving intent choices unchanged. Validate IDs against current-turn sources. Missing/invalid citations on an operational claim trigger a safe template; valid IDs alone do not prove that a statement is supported.

Use a bounded deterministic safety check for unsupported promises, ETAs and instructions. Permit recognized wording only when supported by a matching current source; merely having any announcement is insufficient. If uncertain, use the source text as a quote with a neutral offer to record a request. This guard is heuristic, not a proof of factual entailment. Maintain existing banned-phrase and department checks.

For the library example: “The notice says Wi-Fi is down in the library. It does not give a cause or workaround. Is your problem in the library?” Arabic/Arabizi input gets the existing Arabic response convention. No “our team is working on it” or “use the lab network” unless the source explicitly says so.

Retry at the OpenRouter client/transport boundary BEFORE `CachedChat` converts errors to None. Give the chat agent its own retry-enabled client; shared translation/oracle clients retain their behavior. Preserve typed status/timeout information rather than parsing error strings. At most two total attempts for 429, 5xx or transport timeout, with an injected sleeper and roughly one second delay. No retry for 400, 401, 402, parse/schema failure or exhausted budget. Respect a longer Retry-After by falling back rather than waiting beyond the chat budget. Both attempts consume the same overall deadline and budget accounting; record attempts without caching failures.

Acceptance: fake transport proves retry counts and no retries on excluded errors; cached success avoids transport; exhausted retry returns the existing fallback form. Six scripted cases cover library scope mismatch, missing cause, unsupported workaround, unsupported ETA, valid quoted workaround and hostile source text. Include EN/AR/Arabizi variants and both reply/phrase paths. Real-key regression remains a separately reported manual check.

## 5. P10.3: shared reports, confirmation and announcements

### Product rules

1. Only confirmed reports count. Preview, chatting and declining create no report or ticket.
2. Shared eligibility requires Facilities, IT Support or Transportation AND an explicit shared fault/outage cue. Personal-account/fee/grade/registration cues veto automatic grouping. Ambiguous messages stay individual or ask for clarification. A validated LLM group cue is supplementary; its absence must still allow explicit rule-based outages.
3. Safety alerts and distress flows bypass duplicate suppression and keep their current immediate handling.
4. “No duplicate ticket” means no additional office/Linear issue for a joined report. Each reporter retains a local request and `merged` ticket, visible in My Requests and connected to the shared incident.
5. Existing incident creation threshold and announcement suggestion threshold are distinct. Preserve three reports for incident creation initially; suggest an announcement at FOUR distinct reporters (“more than three”). Repeated requests by one alias do not inflate either threshold.
6. Separate request is an explicit signed choice. It bypasses merge for that submission and is excluded from automatic re-absorption and shared counts.

### Matching and schema

Use the existing embedding, centroid detector and incident actions. Introduce `SharedIssueEligibility` and read-only `KnownIssueMatcher` services; do not reclassify with a new LLM. Eligibility must filter historical candidates too, so earlier personal reports cannot enter a new cluster.

KnownIssueMatcher takes normalized text/embedding/location and returns at most one `KnownIssueMatch(incident_id?, announcement_id?, title, source_excerpt, scope, similarity)` or None. Never match on category alone. When matches are ambiguous, ask one location/detail question instead of choosing arbitrarily.

Migration 0017 permits an unknown incident building and adds explicit scope (`building`, `campus`, `unknown`) plus optional linked announcement. Unknown is not a wildcard: a building-specific issue cannot silently absorb a report with missing or conflicting location. Unknown-location reports may cluster together when they describe the same shared issue; joining a known building requires confirmation of that location. Cross-building joining requires an explicitly campus-wide incident/announcement. Update domain types, SQL/vector filters and map UI: unknown/campus incidents appear in lists, without a fabricated map coordinate.

Persist per-request merge disposition (`automatic`, `joined`, `separate`) and membership uniqueness. Reuse existing incident membership if possible; otherwise add a service-owned membership table with unique request ID and a unique reporter contribution per incident. Membership and count updates must be atomic. Preserve actual reports even when their reporter has already contributed to the distinct count.

Proposed online configuration: `shared_issues.enabled=false`, `window_minutes=120`, `incident_min_reporters=3`, `announcement_min_reporters=4`, and separate candidate/known-match similarity thresholds initialized to the existing 0.92 as a baseline only. Evaluate thresholds on synthetic positive/negative probes before enabling; report the chosen values. Do not modify frozen model config for online clustering. Do not merge open incidents solely because their centroids drift close; scope and eligibility must also agree.

### Proposal and confirmation contract

Extend proposal response with nullable `known_issue`, `choices` and signed tokens per choice. Choices are `record`, `join_known`, `record_separately`; an ordinary proposal has only record. Existing `POST /v1/chat/confirm` still accepts `{proposal_token}`. Each token binds alias, request text, intended action, target IDs, scope/location decision and expiry. UI displays “Add my report” and “Record a separate request” for a known match. Free-text confirmation chooses the default displayed choice only; it must not infer a separate-request override.

Use a persistent confirmation claim/result keyed by token digest (0017, service only), replacing process-only replay protection for this flow. Concurrent/repeated confirmation returns the same completed result; an in-progress claim returns a retryable conflict. Tie request creation to the claim so a crash cannot create another local request on retry. Use that stable request ID for existing sink idempotency; external failures follow existing recorded retry semantics.

On confirmation revalidate scope, live announcement status and incident status. An expired/resolved target returns a replacement proposal requiring confirmation, with no silent conversion to a new ticket. A standalone live announcement can be matched; on first confirmed join atomically create/link its shared incident and parent ticket, then attach the report. Unique announcement-to-incident linkage prevents concurrent first reports making duplicate parents.

When enough confirmed standalone reports form a cluster, retain existing behavior: create the incident parent, move earlier member tickets to merged and mark earlier Linear issues duplicate. The no-duplicate guarantee applies to confirmed joins after a known match; it cannot erase issues already created before a cluster existed.

Joined reports still get lifecycle records and a suitable confirmation message. Do not run ordinary “new office ticket” emails or duplicate parent creation for a member. Incident resolution updates member records and notifies reporters using existing semantics. A separate request keeps its own normal lifecycle.

### Drafts and publication

At four distinct reporters create ONE draft per incident, with majority office (tie: keep the current incident office). A deterministic draft quotes the observed problem, scope and report count; it includes no inferred cause, fix or ETA. Staff of that office or an admin may edit, publish or dismiss it. No automatic publication. Dismissal prevents regenerating the same draft on the fifth report.

Add a separate `announcement_drafts` table rather than putting unpublished rows into the existing student-readable announcement query. Fields: incident_id unique, office, title, body, scope/building, status pending/published/dismissed, version, timestamps, author, published_announcement_id. Staff office/admin RLS only; writes through service-role API with actor checks.

Routes: `GET /v1/announcement-drafts`, `PATCH /v1/announcement-drafts/{id}` with version, `POST /v1/announcement-drafts/{id}/publish` with version, and `POST /v1/announcement-drafts/{id}/dismiss`. Stale versions return 409. Publish atomically inserts one live announcement, links it, changes draft status and creates a broadcast job. Repeated publish returns the same announcement/job; editing an already published notice does not resend automatically.

Publication audience: all student/staff profiles with current consent plus explicitly configured demo student/office inboxes that pass policy. A bare address in the allow-list is permission, not automatic subscription. Deduplicate by normalized address; send separate messages, never expose recipient lists. Re-check authorization at send time. Use a durable job and delivery ledger with unique `(announcement_id, normalized_recipient)`; reserve work atomically, throttle (proposed 10/minute), honor SMTP daily cap and retry recorded transient failures. An SMTP acceptance followed by a process crash can still cause redelivery; document this unavoidable SMTP limitation rather than claiming exactly-once email.

### Required examples / acceptance

| Scenario | Expected result |
|---|---|
| Two people report library Wi-Fi with different wording | Two confirmed contributions; no draft yet |
| Third matching distinct reporter | Shared parent incident; earlier issues marked duplicate |
| Fourth matching distinct reporter | One editable draft for majority office |
| Same reporter repeats three times | No increase in distinct reporter threshold |
| “My account cannot log in” from several people | Personal reports stay separate unless a distinct shared outage is established through clarification |
| “Wi-Fi is down” while only library notice exists | Ask location; no campus-wide claim or silent join |
| Unknown-location shared reports with matching problem | May cluster in unknown scope; list visible, no map pin |
| Matching known issue, Add my report | Local merged record, existing parent, no new Linear issue |
| Matching known issue, Record separately | Own ticket, never immediately reabsorbed |
| Notice archived after preview | Replacement proposal; no mutation without confirmation |
| Concurrent confirms/publishes | One local request per token, one publication/job per draft |
| Staff publishes | Students and staff receive eligible, throttled, deduplicated emails |
| Database, matcher or LLM unavailable | Safe fallback; never claim a report was joined unless persistence succeeded |

## 6. Integration and handoff gates

The integrator checks package contracts before merging and runs the existing required backend and web gates: ruff, strict mypy, default pytest, web lint/typecheck/vitest; contract export/docs checks when API shapes change. Add focused integration tests for confirmation through incident actions and policy through SMTP. Keep unit and integration tests on fake external services.

Update `docs/api/`, `docs/db/schema.md`, `docs/ui/README.md`, `.env.example`, README disclosures and `docs/streams/CHANGELOG.md` with as-built behavior. Package reports identify discrepancies from this architecture before making a scope change. SQL 0016/0017 are supplied to the user for SQL editor application and later migration-history recording, consistent with the existing P10 decision. Do not edit frozen 0013–0015.

Final manual checklist after deployment is separately authorized: profile consent/remove; grounded library conversation; fallback after LLM failure; four distinct demo accounts form a shared incident/draft; join versus separate; staff publishes; recipient/exclusion checks; incident resolution. Record actual outcomes and do not substitute old P9 test counts for this gate.

Agent dispatch template: “Implement package <letter> from docs/plan/p10/ARCHITECTURE.md. Read its dependencies' reports, obey exclusive file ownership, implement only that package, use fake external services, run its acceptance checks and write <package>_report.md. Do not use organizer-only evaluation material, deploy, send live emails, apply SQL or push. Stop with a concrete contract conflict if a required dependency disagrees with this architecture.”
