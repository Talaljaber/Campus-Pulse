# Chat context, classification preparation, and complete ticket handoff

Status: implementation in progress following user authorization. Date: 2026-11-05.

Implementation checkpoint: proposal boundaries no longer erase the original user problem. A typed context
preparation port, cached JSON LLM adapter, campus-aware prompt, and chat wiring have been added behind
`issue_context_enabled: false`. Focused tests: 40 passing; strict backend type check: 226 modules passing.
This is not yet the full implementation: server-owned conversation snapshots, stale-proposal invalidation,
priority recommendation application, full evidence persistence, consistent frozen confirmation decisions,
long-history handling, and end-to-end evaluation remain outstanding. No migration has been applied and
the running services have not been restarted for these changes. The disabled flag prevents activating the
unfinished new preparation path. Priority recommendations are parsed/validated, not applied yet.

## 1. Intended behavior

Every incoming user chat message, including English, goes through an LLM context-preparation step before normal intent handling and classification. The LLM reads the current issue's conversation, resolves short clarifications against earlier questions, produces a concise dataset-style request, and recommends a priority with supporting evidence. The trained model classifies that request. A confirmed ticket contains a complete, grounded summary of the issue rather than the last conversational fragment.

The same issue snapshot must drive the proposal, final classification, ticket description, staff view, and notification content. Confirmation must not regenerate a different summary or classify the word “yes”. Existing safety handling may interrupt immediately before any remote LLM call; it must never wait for a network round trip.

UI redesign is out of scope. Only contract wiring and displaying the issue text for confirmation are included.

## 2. Findings in the current implementation

- `application/use_cases/chat.py`: `turn()` first classifies `last.content`; `_answer()` then calls `_request_text(messages)` for request intent. This is not universally last-message-only: it concatenates user messages, but drops all messages before the last assistant `proposal` OR `ticket` marker. A proposal is not an issue boundary, so a subsequent clarification can discard the original problem.
- `_request_text()` and `_propose()` keep only the last 1,000 characters. Long conversations can lose their opening problem and preserve incidental follow-up details instead.
- `adapters/llm/chat_agent.py` independently keeps only 12 messages. `ChatTurnRequest` accepts 20. These two history limits are inconsistent and neither preserves an explicit issue state.
- `chat_ports.py` currently lets the conversational LLM return reply, intent and source IDs only. It cannot supply a validated issue representation or priority recommendation.
- `proposals.py` signs the proposal text and labels. Confirmation re-runs triage on `claims.text`; summary text already lost upstream cannot be recovered there.
- `config/prompts/understand_v1.md` already creates ticket title/body and bilingual summaries AFTER classification. It sees one request text, so adding a better ticket prompt alone cannot restore missing history.
- `application/use_cases/act.py` already consumes understanding for ticket content. This is the integration point to reuse, not a reason to introduce a separate ticket-writing path.
- Training examples in `data/clean/train_clean.csv` use short concrete requests: “حسابي الجامعي تسكر وعندي امتحان اونلاين اليوم”, “I need a copy of my payment receipt”, and “The system removed my registered course without warning”. Classifier input should resemble this style, not a narrative about a conversation.

These are code-level findings; reproduce the user's exact failure with a regression conversation during implementation before claiming the full runtime cause is verified.

## 3. Proposed flow and ownership

1. Authenticate and validate incoming message; assign stable conversation/message IDs and server timestamps.
2. Run the existing immediate safety path on original input. Preserve original text for safety and abuse checks even when the summary is shorter.
3. Load the current issue snapshot and relevant history, including assistant questions and the newest user answer.
4. Call a dedicated `IssueContextPreparer` LLM adapter for every user message, irrespective of language or apparent simplicity. A retry of the same message can reuse its completed result; a new message must receive a new context evaluation.
5. Validate its structured output, provenance, lengths, known entities, and issue boundary. Keep user facts separate from assistant suggestions and campus reference facts.
6. For ordinary conversation, greeting, or pure confirmation: use the preparation result for intent/context, but do not run the trained classifier unnecessarily. For a changed or new issue ready for classification, send ONLY `classifier_text` through the trained classifier's normal normalization/model pipeline.
7. Combine model priority with a validated evidence-based recommendation through one explicit priority policy. The model remains the source of category and office routing.
8. Ask a focused clarification if essential facts are missing; otherwise generate and show the issue summary/proposal and sign its immutable snapshot reference.
9. On explicit confirmation, create the ticket from that exact snapshot and record the chosen summary and decision provenance. A new LLM summary is needed when issue facts change, not after the user has confirmed a frozen proposal.

The context call should be distinct from the existing post-classification understander. Initially keep conversational reply generation separate for testability; later combine calls only after correctness and latency evaluation. Do not run recursive context preparation inside classifier, preview, confirmation, and understanding.

## 4. Structured context contract

Introduce an application port and immutable `PreparedIssue` value, with a strict adapter schema:

| Field | Meaning |
| --- | --- |
| conversation_id, issue_id, revision | Server-owned identity and revision; never accepted as authority from model output |
| intent | chat, clarify, request, confirm, decline, or new_issue |
| classifier_text | One or two short, factual request sentences; target 30–90 words, maximum 1,000 characters, validated before classification |
| summary_en, summary_ar | Standalone staff-readable account of the issue; no fabricated facts |
| title_en | Short title, maximum 80 characters to match existing understanding limits |
| facts | Problem, affected service, impact, location, relevant course, time/deadline, attempted steps, unresolved questions |
| evidence | Message IDs and exact supporting spans for extracted facts and priority rationale |
| entities | Building code, room, system, deadline as stated, optional resolved deadline and timezone |
| priority_recommendation | low/medium/high or null, concrete reason, evidence IDs, timing certainty |
| readiness | ready or needs_clarification, with one targeted question where necessary |
| supersedes_proposal | Whether new facts invalidate the pending proposal; server validates this against the revision |
| versions | Context prompt, campus knowledge, model, schema; attached by server |

Do not insert category guesses, numeric model scores, “high priority”, routing instructions, or LLM reasoning into `classifier_text`. Store priority recommendation alongside the text, not embedded in it. Unknown entity values remain null. Source references must exist in the current issue history. Reject unsupported quotations/IDs; semantic consistency still needs curated evaluation because matching a quote alone does not prove a claim.

## 5. Dataset-style summarization rules

- Describe the user's current problem in direct request language, retaining the affected operation, failure, impact, and actual timing.
- Exclude greetings, confirmation words, repeated questions, assistant advice, unrelated earlier issues, and narration such as “the student discussed…”.
- Preserve negation and corrections: “not an exam”, “tomorrow, not today”, “Teams works; Outlook does not”. Later explicit corrections supersede earlier facts and retain provenance.
- Resolve short answers using the question: “L” after “Which building?” becomes library building L; “today” after “When is the exam?” becomes an exam today. Do not attach ambiguous answers to an invented question.
- Keep English requests in English, Arabic in Arabic, and normalize Arabizi according to the existing evaluated language pipeline. Evaluate mixed-language normalization against the original model before choosing a universal language conversion.
- Preserve safety evidence outside the summary even if compression omits it. A normalizer cannot erase risk or manipulation evidence by rewriting it.
- Do not truncate a completed summary blindly. If over length, request one bounded correction, then use the defined failure path.

Example: user “I can't log in”; assistant “Which service?”; user “e learning”; assistant “Does this block something due soon?”; user “my exam starts in 20 minutes in L”. Classifier input: “I cannot log in to e-learning and my online exam starts in 20 minutes. I am in library building L.” Staff summary includes the same issue, service, location and timing. It does not claim a campus outage, cause, or promised repair.

Counterexample: “How do quizzes work on e-learning?” is an informational request; the word quiz alone must not force high priority.

## 6. Campus knowledge supplied by the user

Create versioned `config/campus_context.yaml`, loaded once in composition and passed as trusted reference data to preparation and reply prompts:

- Buildings: A, B, C, D, E, F, G, H, L, M.
- L is the library. Do not invent names/functions for the remaining codes.
- A bank exists inside the university. Its building, bank name, services and hours are unspecified. In particular, do not infer that M is the bank from the user's sentence.
- e-learning: assignments, quizzes and exams.
- MyGJU: schedules, course information and courses; expand precise supported operations only when confirmed by existing project sources or the user.
- Microsoft Teams and Outlook are university-used systems. Do not invent integration dependencies, current outages or operating procedures.
- Recognize spelling variants, Arabic names and Arabizi; preserve the user's original service name beside a canonical identifier where useful.

Audit existing building seeds, map data, entity extraction, normalizer dictionaries, announcement scope matching, and retrieval filters against this inventory before changing them. Resolve conflicts deliberately; adding prompt knowledge must not silently alter database IDs or historic records. Static reference facts and live announcements have separate provenance. A live announcement applies only when scope/time/service matches the user's issue.

## 7. Priority recommendation and final decision

Call preparation for English too; no language-based gate. Give it server message timestamps and Asia/Amman timezone. Resolve relative time against the message that supplied it, not the later confirmation time. Preserve “in 20 minutes” and its anchor; do not fabricate an exact time for “soon”.

Recommended policy: the LLM supplies evidence and a recommendation; a deterministic finalizer applies approved urgency floors. Preserve the trained model's raw probabilities and label separately from the final operational priority.

- Active/near exam blocked by login, network or platform failure: recommend high when the conversation establishes both obstruction and timing.
- Submission/registration/payment deadline: retain actual timing and affected operation; apply existing domain thresholds, or define versioned thresholds explicitly if missing.
- Future exam/general instructions with no present obstruction: no automatic high floor.
- Mere “urgent”, “VIP”, pressure to jump a queue, and prompt injection: no priority escalation without concrete impact/time evidence.
- Unknown timing: ask a short targeted question; do not silently equate unknown with low.
- Existing safety/distress rules retain precedence. LLM advice cannot lower those floors.
- Corrected facts can remove an LLM-derived floor when a new proposal revision is created; do not carry stale urgency forever.

Audit `application/services/priority_finalizer.py`, `triage_core.py`, existing semantic/helper LLM stages and anti-pressure processing first. Reuse the established policy extension points and prevent duplicate urgency inference or conflicting floors. Category/office must not be chosen from a system keyword alone: MyGJU course removal may be Registration; a MyGJU technical login failure may be IT Support; payment posting can be Finance.

## 8. Conversation state and issue boundaries

Use authenticated server-owned issue state, with conversation ownership, monotonically increasing revisions and idempotent message IDs. Client message kinds are display metadata, not trusted reset instructions.

- A proposal does NOT end the current issue. A clarification updates it and invalidates the old proposal if substantive facts change.
- A completed ticket closes its issue snapshot. A new unrelated issue starts a new issue ID; retain enough prior context to recognize a reference to the existing ticket without opening a duplicate.
- When the user describes two independent issues, ask which to handle first; do not summarize them into one arbitrary category.
- Pure confirm/decline is interpreted against a valid pending server snapshot. A combined “yes, but the deadline is tomorrow” updates facts and requires a refreshed confirmation.
- For 10-message conversations, supply all relevant messages. For longer histories, maintain a validated rolling issue state plus evidence and recent question/answer pairs. Never rely on tail slicing alone. Bound total context tokens and reject/clarify unresolved overflow.
- Serialize simultaneous updates or enforce optimistic revision checks; delayed LLM replies cannot overwrite a newer issue.

Proposed persistence: a conversation/issue snapshot store with owner, revision, structured preparation, message evidence, prompt versions, TTL and proposal linkage. Exact schema and migration numbering require inspecting current migrations during implementation. Define access control and retention, avoid secrets/credentials and unnecessary personal details, and keep operational logs free of raw chat bodies.

## 9. Proposal and ticket consistency

Prefer a signed token containing owner/alias, issue ID, snapshot revision/hash, expiry and nonce instead of embedding growing summaries in the existing 4,000-character token limit. Verify ownership and revision on confirmation and reuse durable claim handling.

Classify once per prepared issue revision. Persist the classification and policy/artifact versions with the proposal. Confirmation should execute the reviewed decision, or explicitly require a refreshed proposal if reclassification becomes necessary; do not silently change category or priority between preview and ticket creation.

Populate existing title/body and bilingual summary fields from the approved structured facts through the understanding contract. Keep ticket wording independent of an LLM call that might fail after confirmation: the frozen snapshot already contains a usable title/body or enough grounded data for a deterministic renderer. Original conversation evidence remains separately available for authorized diagnostics, never presented as a generated quotation from the user.

Verify staff ticket detail, initial activity, email/notification and integration payloads all consume the same complete issue description. No outbound messages are sent during planning or tests; use fakes/sinks.

## 10. Failure behavior, latency and observability

- Invalid JSON, unsupported facts, timeout or unavailable LLM: one bounded retry within an overall budget, then preserve the issue and request a complete description or offer the existing form. Never classify a context-dependent fragment as if it were the full issue.
- A self-contained plain-form request can use the existing deterministic fallback, explicitly tracked as degraded. Safety handling stays available regardless of LLM availability.
- Keep a pending valid proposal intact during an unrelated network failure; never create a ticket merely because summarization succeeded.
- Cache by conversation/issue revision, full relevant history hash, language, campus knowledge version, prompt/model version and temporal anchor. Do not share cached personalized results across users.
- Budget preparation, reply generation, model inference and post-processing against the existing web proxy timeout (20 seconds by default). Measure p50/p95 and cost per turn; avoid three independent retries multiplying latency. Adjust API/client timeouts together only with measured justification.
- Record preparation outcome, latency, token usage, fallback reason, model priority, recommendation, applied rule and snapshot hash. Retain model scores separately to avoid misreporting deterministic adjustments as confidence.

## 11. Implementation work packages

1. Reproduce and baseline: build multi-turn fixtures for loss after a proposal and 1,000-character truncation; trace raw request through ticket body. Audit frontend wire history limits and existing helper LLM execution conditions.
2. Contracts/knowledge: add strict preparation port/value/schema, campus registry and versioned context prompt with train-only examples. Add bounded source validation and temporal parsing.
3. State: implement authenticated issue store, revision/idempotency handling and proposal snapshot linkage. Provide migration/backfill strategy; existing tickets remain unchanged.
4. Orchestration: invoke preparation for every user chat turn; replace `_request_text` logic; handle clarification and issue boundaries; route single-turn live triage through equivalent preparation where required while keeping offline benchmark mode explicit and reproducible.
5. Decision policy: connect canonical text to the trained classifier and evidence-backed priority advice to the existing finalizer. Remove duplicate helper calls only after proving equivalent behavior.
6. Confirmation/handoff: bind proposal and ticket to one snapshot; reuse understanding/Act pipeline, durable claims, and complete staff/notification content. Add backwards-compatible token verification or explicitly expire pre-rollout proposals with a clear retry message.
7. Contract integration: update DTOs, API contracts, OpenAPI generation and frontend wire conversion only as required. Preserve user confirmation and fallback form behavior.
8. Evaluation and rollout: run the acceptance suite, enable behind a dedicated flag for all languages, observe shadow comparisons, then promote. Roll back via flag; retain original model artifacts and old prompt versions.

Likely existing files: `application/use_cases/chat.py`, `chat_ports.py`, `proposals.py`, `triage.py`, `act.py`; `application/services/triage_core.py`, `priority_finalizer.py`, `understanding.py`; `adapters/llm/chat_agent.py`, `cached_chat.py`; `adapters/understand/*`; `composition/chat.py`, `composition/online.py`; DTO/API contract files; `apps/web/src/hooks/useAgent.ts` and chat transport/reducer files. New files should follow existing application-port/adapter/composition boundaries. No direct provider calls from domain policy or frontend.

## 12. Acceptance and evaluation

Required deterministic integration cases:

- Initial problem + service + building + deadline over 10 messages yields one complete classification input and ticket.
- Proposal followed by “actually L” preserves the initial issue, replaces the location, and expires the old proposal.
- Original issue longer than 1,000 characters remains represented; short answers and “yes” never become standalone tickets.
- Pure confirmation makes no new issue summary and creates exactly one ticket under retries/concurrent submits.
- English, Arabic, Arabizi and mixed-language turns all invoke preparation; identical failed request retries are idempotent.
- e-learning exam now versus exam next month versus a general quiz question; MyGJU login versus course removal; Teams versus Outlook distinctions.
- Building L resolves to library; unknown room/building and bank location remain unknown; M is never automatically treated as bank.
- Negation, corrected deadlines, cancelled exams, multiple unrelated issues, misleading assistant suggestions and prompt injection do not pollute facts or priority.
- LLM outage/invalid schema, expired snapshots, stale replies, wrong-owner tokens and missing store state fail predictably without corrupting a ticket.
- Immediate safety handling works with LLM unavailable; summary compression cannot suppress distress evidence.
- Staff detail, notification and outbound payload fixtures contain the original issue and relevant clarifications.

Evaluation uses held-out multi-turn fixtures and existing validation splits; prompts/examples come only from the training split. Do not use organizer hidden test labels for prompt tuning. Compare raw single-turn baseline, concatenated history and prepared summaries using category macro-F1, priority macro-F1, high-priority recall, false-high rate, summary fact omission/hallucination rate, ticket completeness, latency and cost. Report per language and per system, not just aggregate accuracy. Existing single-turn validation must remain a separate benchmark from the new conversational evaluation.

Release gates: all ownership/idempotency/context-preservation integration cases pass; zero invented critical deadlines/locations in curated cases; every curated ticket is understandable without the last chat message; no unexplained category/priority regression against the frozen baseline. Set numeric non-regression tolerance and latency/cost budgets from the measured baseline before rollout, not after observing candidate results. Build/type checks, focused backend tests and generated-contract checks must pass.

## 13. Decisions and remaining uncertainties

Adopt: LLM context preparation on every incoming user message; trained classifier receives dataset-style issue text; priority recommendation is evidence-based advisory input with deterministic final authority; tickets and proposals share an immutable issue snapshot; confirmation reuses the prepared summary.

Unspecified: bank building/name, functions of buildings other than L, exact urgency thresholds beyond existing policy, persistence retention period and latency budget. Keep these configurable or unknown; they do not block architecture work. The user's campus facts are the initial knowledge source, not a claim that all existing project seed data has already been reconciled.

Completion of this planning task means this file only. Implementation, migrations, model calls, server restarts and edits to application code are intentionally deferred to a subsequent request.

## 14. Follow-up decisions, 2026-11-05 (user-directed)

- The preparation step is on (`issue_context_enabled: true`, prompt `config/prompts/issue_context_v2.md`) for every
  message, English included. The chat prompt is `chat_agent_v3.md`.
- `classifier_text` is now always plain English (Arabic and Arabizi are translated). This replaces the earlier
  "keep Arabic in Arabic" rule of section 5. Evidence on ten Arabic/Arabizi messages: with an English rewrite all ten
  got one confident category and the automatic route; with the Arabic wording most got 2 to 5 categories and went to
  ask, review or the topic menu (offline classifier, conformal sets). The student's reply stays in their language.
  Known cost: the stored request text is the English rewrite, not the student's own words (section 9's "original
  evidence" is still open).
- The campus facts now say M is the bank inside the university (the user's wording; Codex had left M unknown).
- The priority recommendation is applied, raise-only: in the proposal, and again at confirmation through
  `TicketLifecycleUseCase.raise_priority`. A message flagged `injection` or `queue_jump` never gets the raise.
- A failing preparation no longer drops the chat to the plain form: the turn continues with the plain request text.
  The reply call and the preparation call run side by side.
- Known limit: a MyGJU problem about a record (a missing course, a payment not showing) still tilts to IT Support
  because the website name is in the sentence; staff forwarding corrects it.

## 15. One student, one issue, one ticket (2026-11-05, user-directed)

Problem seen: the same student ended up with three open e-learning tickets in one conversation, and a follow-up
("I also have an exam") proposed another ticket instead of changing the first.

- Before a proposal, the chat reads the caller's own open tickets (`Repository.open_tickets_for_alias`, status new or
  in progress, newest first, at most 5) and passes them to the issue preparer, which may answer `duplicate_of` with
  one listed ticket number (a repeat, or only extra detail or urgency). The adapter drops any number it was not given.
  Without the preparer, a request whose normalized words equal an open ticket's text counts as a repeat too.
- A repeat never opens a second ticket. If the new priority (model, plus the evidence-backed recommendation) is higher
  than the open ticket's, the ticket is raised (`TicketLifecycleUseCase.raise_priority`, new or in progress, system
  actor, clock restarts, a `priority` activity row) and the student is told. Otherwise the student is told which
  ticket is already open and at what priority. A different category from the open ticket, or a pending
  clarification question, means the message is treated as a new request.
- At confirmation, a token whose text equals another open ticket of the same student is refused
  (`DuplicateOpenTicket`, 422 on the plain-form endpoint, the "already open" reply in the chat). The ticket made by the
  same token never counts, so a repeated confirm still returns its stored result.
- Not done: the student's follow-up words are not added to the existing ticket as a comment, and the office is not
  emailed when a priority is raised this way (it shows in the queue and in the ticket thread). Tickets that were
  already duplicated before this change are untouched.

