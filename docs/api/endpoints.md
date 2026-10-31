# API endpoints

> **Generated** by `python scripts/gen_api_docs.py` from `services/ai/openapi.json` and `services/ai/tests/fixtures/api/*.json`. Do not edit by hand; CI runs `--check`.
> Auth, status values, flags, error codes and versioning: [README.md](README.md).

API version `0.1.0`, OpenAPI `3.1.0`. Examples use PowerShell with `curl.exe`; set `$env:AI_URL` (no trailing slash), `$env:AI_SERVICE_TOKEN` and, for user calls, `$env:USER_JWT` (the user's Supabase access token). Request bodies are read from a file (`--data-binary "@request.json"`) because PowerShell 5.1 mangles inline JSON quotes.

Every non-2xx response has this shape:

```json
{
  "error": {
    "code": "<error code>",
    "message": "<human-readable>",
    "details": null
  }
}
```

## Contents

- [`POST /v1/triage`](#triage) Triage one request
- [`POST /v1/triage/{request_id}/clarify`](#clarify) Answer a clarifying question
- [`GET /v1/explain/{request_id}/counterfactual`](#explain_counterfactual) Live counterfactual
- [`POST /v1/feedback`](#feedback) Staff confirm or correct a prediction
- [`POST /v1/tickets/{ticket_id}/status`](#ticket_status) Change a ticket's status from the dashboard
- [`GET /v1/incidents`](#list_incidents) List incidents
- [`POST /v1/incidents/{incident_id}/resolve`](#resolve_incident) Resolve an incident and notify reporters
- [`GET /v1/insights/recurring`](#insights_recurring) Recurring problems
- [`POST /v1/integrations/linear/webhook`](#linear_webhook) Inbound Linear status sync
- [`POST /v1/batch`](#batch) Batch predictions from a CSV
- [`POST /v1/redteam/run`](#redteam_run) Run the red team
- [`GET /v1/metrics`](#metrics) Model lab metrics
- [`GET /v1/health`](#health) Health
- [`GET /health`](#health_root) Health (root alias)
- [`POST /v1/admin/simulate`](#admin_simulate) Start simulated Pulse traffic (optional extra)
- [`POST /v1/admin/reindex`](#admin_reindex) Re-embed a vector collection (optional extra)
- [Schemas](#schemas)

<a id="triage"></a>
## `POST /v1/triage`

**Triage one request.** Runs the main flow (SPEC §5.1) for one student message: normalize, guards, ensemble, conformal sets, decision policy, then either a clarifying question or a decision with explanation, understanding and action.

- **Roles:** `student`, `staff`, `admin`, `service`
- **Auth:** service token

**Parameters**

| Name | In | Type | Required | Notes |
| --- | --- | --- | --- | --- |
| `debug` | query | `"members"` \| null | no | `members` fills `explanation.trace.per_model` (admin only, P5.16). |

Identity headers: `X-CP-User-JWT` (see [README › Auth](README.md#auth)).

**Request body**

`application/json`: [TriageRequest](#schema-triagerequest)

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `text` | string | yes | The student's message (or the confirmed voice transcript); min len 1 |
| `input_mode` | `text` \| `voice` | no | default `"text"` |
| `student_alias` | string | no | Pseudonymous alias such as `demo-17`; never a name; default `""` |
| `location` | [LocationIn](#schema-locationin) \| null | no |  |
| `conversation_id` | string \| null | no |  |
| `simulated` | boolean | no | True only for `scripts/simulate_pulse.py` traffic (P4.10); default `false` |

**Response `200`:** `application/json` [TriageResponse](#schema-triageresponse)

**Example** (fixture `triage_decided_en_faq`): English information request answered from the FAQ (Transportation x low). Default triage fixture.

`request.json`:

```json
{
  "text": "where is the bus timetable for the Madaba route?",
  "student_alias": "demo-17"
}
```

```powershell
curl.exe -s -X POST "$env:AI_URL/v1/triage" `
  -H "Authorization: Bearer $env:AI_SERVICE_TOKEN" `
  -H "X-CP-User-JWT: $env:USER_JWT" `
  -H "Content-Type: application/json" `
  --data-binary "@request.json"
```

Response `200`:

```json
{
  "request_id": "5b0e7c52-3f0a-4d8e-9c41-0a1b2c3d0002",
  "status": "decided",
  "lang": "en",
  "is_arabizi": false,
  "understood_as": null,
  "category": {
    "label": "Transportation",
    "prob": 0.94,
    "set": [
      "Transportation"
    ]
  },
  "priority": {
    "label": "low",
    "prob": 0.88,
    "set": [
      "low"
    ],
    "evidence": [
      {
        "type": "info_request",
        "span": "where is"
      }
    ]
  },
  "tier": "tier0",
  "clarification": null,
  "explanation": {
    "top_tokens": [
      [
        "bus",
        0.34
      ],
      [
        "timetable",
        0.29
      ],
      [
        "route",
        0.11
      ],
      [
        "where",
        0.07
      ],
      [
        "Madaba",
        0.03
      ]
    ],
    "neighbors": [
      {
        "text": "When does the first bus to Amman leave in the morning?",
        "label": "Transportation",
        "priority": "low",
        "sim": 0.83,
        "source": "train",
        "created_at": null
      },
      {
        "text": "وين بلاقي مواعيد الباص؟",
        "label": "Transportation",
        "priority": "low",
        "sim": 0.79,
        "source": "train",
        "created_at": null
      },
      {
        "text": "Is there a shuttle schedule for the weekend?",
        "label": "Transportation",
        "priority": "low",
        "sim": 0.74,
        "source": "train",
        "created_at": null
      }
    ],
    "counterfactual": null,
    "trace": {
      "sets": {
        "cat": 1,
        "pri": 1
      },
      "models_agree": true,
      "cost_usd": 0.0,
      "latency_ms": 96,
      "policy_path": [
        "c_accept"
      ],
      "clarified": false,
      "artifact_version": "v1",
      "per_model": null
    }
  },
  "flags": [],
  "action": {
    "type": "faq_answer",
    "ticket_id": null,
    "external": [],
    "sla_due_at": null,
    "message": "Bus timetables for every route are on the Transport page and at the main bus stop. [demo] Source: https://campuspulse.example.com/faq/transport/bus-timetable",
    "provisional": false,
    "tags": [],
    "booking": null,
    "faq": {
      "question": "Where can I find the bus timetable?",
      "answer": "Bus timetables for every route are on the Transport page and at the main bus stop. [demo]",
      "source_url": "https://campuspulse.example.com/faq/transport/bus-timetable",
      "is_demo": true,
      "score": 0.86
    },
    "incident_id": null
  },
  "message": null,
  "understanding": {
    "summary_en": "Student asks where to find the bus timetable for the Madaba route.",
    "summary_ar": "الطالب بسأل وين يلاقي جدول باصات خط مادبا.",
    "entities": {
      "building": null,
      "room": null,
      "course_code": null,
      "deadline": null,
      "system": "bus timetable"
    },
    "student_reply": "You can find the Madaba route timetable on the Transport page; the link is below.",
    "ticket_title": "Bus timetable request (Madaba route)",
    "ticket_body": "Information request answered from the FAQ; no ticket opened.",
    "source": "rules",
    "prompt_version": null
  }
}
```

**More examples** (send `X-Mock-Fixture: <name>` to the mock app to get one)

| Fixture | Status | What it shows |
| --- | --- | --- |
| `triage_decided_ar_booking` | 200 | Academic Support x high: the earliest fictional advisor slot is booked (UD-1), an email goes to the allow-listed demo inbox, and a ticket is opened. |
| `triage_decided_arabizi_exam` | 200 | Arabizi input: transliterated for the models and echoed in `understood_as`; exam-now evidence makes it high and tags the helpdesk ticket `exam-in-progress`. |
| `triage_decided_en_injection` | 200 | Video moment 3: an injection attempt is flagged and stripped, LLM tiers are skipped (tier0) and the priority is not raised. Student view (staff-only flags removed). |
| `triage_decided_en_safety` | 200 | Physical danger: the safety floor forces high, the action is a safety alert plus a maintenance ticket. |
| `triage_decided_en_tier1_memory` | 200 | Escalated to tier 1 (set-constrained, cached and costed); the nearest neighbour is a staff correction from live memory. |
| `triage_distress_ar` | 200 | Distress signal: no classification, no ticket, no email, no LLM. Supportive message with the counselling placeholder and 911; an immediate human-review item is queued. |
| `triage_error_empty_text` | 422 | Empty text is rejected with the standard error body (422 invalid_input). |
| `triage_error_no_token` | 401 | No `Authorization: Bearer` service token (the browser called FastAPI directly instead of the Next.js proxy): 401 unauthenticated. |
| `triage_human_review_en` | 200 | Two issues in one message: three categories stay in the set after tier 1, so a staff member reviews it; a provisional (unconfirmed) ticket is opened with the best guess. |
| `triage_needs_clarification_ar` | 200 | Video moment 1, step 1: Jordanian Arabic, ambiguous between Registration and IT Support, so the policy asks one question (rule d_ask). |
| `triage_out_of_scope_en` | 200 | Off-topic request (OOD score below tau_ood with a wide set): no labels, a rephrase message and topic chips in `clarification` (question_id `topic`). |

Error example (`triage_error_empty_text`, 422):

```json
{
  "error": {
    "code": "invalid_input",
    "message": "Request validation failed.",
    "details": {
      "errors": [
        {
          "loc": [
            "body",
            "text"
          ],
          "msg": "String should have at least 1 character",
          "type": "string_too_short"
        }
      ]
    }
  }
}
```

**Errors**

| HTTP | Codes |
| --- | --- |
| 422 | `invalid_input`: Body, query or path failed validation, or the use case raised InvalidInput. |
| 503 | `artifact_unavailable`: The frozen model artifact is missing or failed its checksum. `store_unavailable`: Supabase or the vector store is unreachable. |
| 401 | `unauthenticated`: Missing or wrong service token (or a bad webhook signature). |
| 500 | `internal_error`: Unexpected failure; no stack trace is returned. |

**Side effects**

- inserts `requests`, `predictions` and `events` rows; upserts the request embedding into the `requests` vector collection
- needs_clarification: inserts a `clarifications` row
- decided/human_review: opens a ticket (Supabase + Linear issue), may book an advisor slot, sends allow-listed email and in-app notifications (`outbox` rows), may create or attach to an incident
- human_review, out_of_scope, distress: inserts a `review_queue` row
- distress: no ticket, no email, no LLM call
- LLM tiers (if escalated) write `llm_calls` rows

<a id="clarify"></a>
## `POST /v1/triage/{request_id}/clarify`

**Answer a clarifying question.** Applies the student's answer (an option chip or free text) to a request in `needs_clarification` and re-runs the core (LD-29). Returns the same shape as /v1/triage.

- **Roles:** `student`, `service`
- **Auth:** service token

**Parameters**

| Name | In | Type | Required | Notes |
| --- | --- | --- | --- | --- |
| `request_id` | path | string | yes |  |

Identity headers: `X-CP-User-JWT` (see [README › Auth](README.md#auth)).

**Request body**

`application/json`: [ClarifyRequest](#schema-clarifyrequest)

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `question_id` | string | yes | min len 1 |
| `option_id` | string \| null | no |  |
| `free_text` | string \| null | no |  |

**Response `200`:** `application/json` [TriageResponse](#schema-triageresponse)

**Example** (fixture `clarify_decided_ar`): Video moment 1, step 2: the student picks 'registration'; the core re-runs with the constraint and the request is decided (Registration x high): Linear issue plus allow-listed email.

`request.json`:

```json
{
  "question_id": "cat:Registration|IT Support",
  "option_id": "registration"
}
```

```powershell
curl.exe -s -X POST "$env:AI_URL/v1/triage/5b0e7c52-3f0a-4d8e-9c41-0a1b2c3d0001/clarify" `
  -H "Authorization: Bearer $env:AI_SERVICE_TOKEN" `
  -H "X-CP-User-JWT: $env:USER_JWT" `
  -H "Content-Type: application/json" `
  --data-binary "@request.json"
```

Response `200`:

```json
{
  "request_id": "5b0e7c52-3f0a-4d8e-9c41-0a1b2c3d0001",
  "status": "decided",
  "lang": "ar",
  "is_arabizi": false,
  "understood_as": null,
  "category": {
    "label": "Registration",
    "prob": 1.0,
    "set": [
      "Registration"
    ]
  },
  "priority": {
    "label": "high",
    "prob": 0.83,
    "set": [
      "high"
    ],
    "evidence": [
      {
        "type": "deadline_today",
        "span": "اليوم آخر يوم"
      },
      {
        "type": "enrollment_blocked",
        "span": "بعطيني خطأ"
      }
    ]
  },
  "tier": "tier0",
  "clarification": null,
  "explanation": {
    "top_tokens": [
      [
        "اليوم",
        0.31
      ],
      [
        "أسجل",
        0.22
      ],
      [
        "خطأ",
        0.14
      ],
      [
        "آخر",
        0.09
      ],
      [
        "CS",
        0.05
      ]
    ],
    "neighbors": [
      {
        "text": "النظام ما خلاني أسجل المادة واليوم آخر يوم للتسجيل",
        "label": "Registration",
        "priority": "high",
        "sim": 0.86,
        "source": "train",
        "created_at": null
      },
      {
        "text": "I can't add CS 201, the registration system rejects me and the deadline is today",
        "label": "Registration",
        "priority": "high",
        "sim": 0.81,
        "source": "train",
        "created_at": null
      },
      {
        "text": "موقع التسجيل مش راضي يفتح معي",
        "label": "IT Support",
        "priority": "medium",
        "sim": 0.74,
        "source": "train",
        "created_at": null
      }
    ],
    "counterfactual": {
      "drop": "اليوم",
      "category": "Registration",
      "priority": "medium"
    },
    "trace": {
      "sets": {
        "cat": 1,
        "pri": 1
      },
      "models_agree": false,
      "cost_usd": 0.0,
      "latency_ms": 412,
      "policy_path": [
        "d_ask",
        "c_accept"
      ],
      "clarified": true,
      "artifact_version": "v1",
      "per_model": null
    }
  },
  "flags": [],
  "action": {
    "type": "ticket",
    "ticket_id": "c1a9e3b7-2d4f-4e6a-9b8c-7d6e5f4a0001",
    "external": [
      {
        "sink": "linear",
        "external_id": "CP-42",
        "url": "https://linear.app/campuspulse-demo/issue/CP-42"
      }
    ],
    "sla_due_at": "2026-11-06T09:05:00+03:00",
    "message": "فتحنا تذكرة مستعجلة لدائرة القبول والتسجيل لنفس اليوم، وبعتنالك إيميل فيه رقم التذكرة.",
    "provisional": false,
    "tags": [
      "same-day"
    ],
    "booking": null,
    "faq": null,
    "incident_id": null
  },
  "message": null,
  "understanding": {
    "summary_en": "Student cannot register for CS 201: the system returns an error and today is the last registration day.",
    "summary_ar": "الطالب مش قادر يسجل مادة CS 201 لأنه النظام بعطيه خطأ، واليوم آخر يوم للتسجيل.",
    "entities": {
      "building": null,
      "room": null,
      "course_code": "CS 201",
      "deadline": "2026-11-05",
      "system": "registration portal"
    },
    "student_reply": "فهمنا عليك: مشكلة بتسجيل CS 201 واليوم آخر يوم. فتحنا تذكرة مستعجلة لدائرة التسجيل ورح يتواصلوا معك اليوم.",
    "ticket_title": "CS 201 registration blocked on the last registration day",
    "ticket_body": "Reported by demo-17: registering for CS 201 fails with a system error; today (2026-11-05) is the last registration day. Clarified as a registration problem, not a login/website outage.",
    "source": "llm",
    "prompt_version": "v1"
  }
}
```

**More examples** (send `X-Mock-Fixture: <name>` to the mock app to get one)

| Fixture | Status | What it shows |
| --- | --- | --- |
| `clarify_error_no_pending_question` | 409 | Clarifying a request that is already decided: 409 clarification_budget_exceeded. |

Error example (`clarify_error_no_pending_question`, 409):

```json
{
  "error": {
    "code": "clarification_budget_exceeded",
    "message": "No clarification question is pending for this request.",
    "details": {
      "request_id": "5b0e7c52-3f0a-4d8e-9c41-0a1b2c3d0002"
    }
  }
}
```

**Errors**

| HTTP | Codes |
| --- | --- |
| 422 | `invalid_input`: Body, query or path failed validation, or the use case raised InvalidInput. |
| 403 | `forbidden`: The caller's role may not use this endpoint (or this office's resource). |
| 404 | `not_found`: The referenced request, prediction, ticket or incident does not exist. |
| 409 | `clarification_budget_exceeded`: No clarification question is pending for this request. |
| 503 | `store_unavailable`: Supabase or the vector store is unreachable. |
| 401 | `unauthenticated`: Missing or wrong service token (or a bad webhook signature). |
| 500 | `internal_error`: Unexpected failure; no stack trace is returned. |

**Side effects**

- updates the `clarifications` row (answer, answered_at)
- then the same side effects as /v1/triage for the new status

<a id="explain_counterfactual"></a>
## `GET /v1/explain/{request_id}/counterfactual`

**Live counterfactual.** Re-classifies the request with one token removed, for the clickable words in the UI.

- **Roles:** `student`, `staff`, `admin`
- **Auth:** service token

**Parameters**

| Name | In | Type | Required | Notes |
| --- | --- | --- | --- | --- |
| `request_id` | path | string | yes |  |
| `drop` | query | string | yes | The token to delete from the request text. |

Identity headers: `X-CP-User-JWT` (see [README › Auth](README.md#auth)).

**Request body**

None.

**Response `200`:** `application/json` [CounterfactualResponse](#schema-counterfactualresponse)

**Example** (fixture `counterfactual_drop_today`): Clicking the highlighted word 'اليوم' in the moment-1 request: without it, priority drops to medium.

```powershell
curl.exe -s -X GET "$env:AI_URL/v1/explain/5b0e7c52-3f0a-4d8e-9c41-0a1b2c3d0001/counterfactual?drop=%D8%A7%D9%84%D9%8A%D9%88%D9%85" `
  -H "Authorization: Bearer $env:AI_SERVICE_TOKEN" `
  -H "X-CP-User-JWT: $env:USER_JWT"
```

Response `200`:

```json
{
  "request_id": "5b0e7c52-3f0a-4d8e-9c41-0a1b2c3d0001",
  "drop": "اليوم",
  "original_category": "Registration",
  "original_priority": "high",
  "category": "Registration",
  "priority": "medium",
  "category_prob": 0.97,
  "priority_prob": 0.66,
  "flipped": true
}
```

**Errors**

| HTTP | Codes |
| --- | --- |
| 422 | `invalid_input`: Body, query or path failed validation, or the use case raised InvalidInput. |
| 403 | `forbidden`: The caller's role may not use this endpoint (or this office's resource). |
| 404 | `not_found`: The referenced request, prediction, ticket or incident does not exist. |
| 401 | `unauthenticated`: Missing or wrong service token (or a bad webhook signature). |
| 500 | `internal_error`: Unexpected failure; no stack trace is returned. |

**Side effects**

- none (read-only; no rows written)

<a id="feedback"></a>
## `POST /v1/feedback`

**Staff confirm or correct a prediction.** Staff confirm or correct category/priority. The prediction becomes final (tier `human`), deferred actions fire, and the example enters live memory immediately (SPEC §5.3).

- **Roles:** `staff`, `admin`
- **Auth:** service token

Identity headers: `X-CP-User-JWT` (see [README › Auth](README.md#auth)).

**Request body**

`application/json`: [FeedbackRequest](#schema-feedbackrequest)

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `prediction_id` | string | yes | min len 1 |
| `corrected_category` | [Category](#schema-category) \| null | no |  |
| `corrected_priority` | [Priority](#schema-priority) \| null | no |  |
| `note` | string | no | default `""` |

**Response `200`:** `application/json` [FeedbackResponse](#schema-feedbackresponse)

**Example** (fixture `feedback_corrected`): Staff correct the human-review request to Registration: the ticket becomes final and the example enters live memory immediately.

`request.json`:

```json
{
  "prediction_id": "8d21f4a0-6c3e-4b7a-8e15-3c4d5e6f0004",
  "corrected_category": "Registration",
  "corrected_priority": null,
  "note": "Account holds are handled by the Registrar after Finance clears the payment."
}
```

```powershell
curl.exe -s -X POST "$env:AI_URL/v1/feedback" `
  -H "Authorization: Bearer $env:AI_SERVICE_TOKEN" `
  -H "X-CP-User-JWT: $env:USER_JWT" `
  -H "Content-Type: application/json" `
  --data-binary "@request.json"
```

Response `200`:

```json
{
  "prediction_id": "8d21f4a0-6c3e-4b7a-8e15-3c4d5e6f0004",
  "request_id": "5b0e7c52-3f0a-4d8e-9c41-0a1b2c3d0004",
  "category": "Registration",
  "priority": "medium",
  "tier": "human",
  "flags": [
    "staff_confirmed"
  ],
  "ticket": {
    "id": "c1a9e3b7-2d4f-4e6a-9b8c-7d6e5f4a0004",
    "request_id": "5b0e7c52-3f0a-4d8e-9c41-0a1b2c3d0004",
    "incident_id": null,
    "office": "Registrar",
    "category": "Registration",
    "priority": "medium",
    "status": "open",
    "provisional": false,
    "sla_due_at": "2026-11-08T10:02:00+03:00",
    "escalated_at": null,
    "resolved_at": null,
    "title": "Account still on hold after fee payment; grades not visible",
    "links": [
      {
        "sink": "linear",
        "external_id": "CP-44",
        "url": "https://linear.app/campuspulse-demo/issue/CP-44"
      }
    ]
  },
  "memory": {
    "example_id": "0b7d9e1f-4a2c-4d3e-8f5a-6b7c8d9e0004",
    "active_examples": 4
  },
  "actions": [],
  "message": "Added to memory: will influence similar requests now."
}
```

**More examples** (send `X-Mock-Fixture: <name>` to the mock app to get one)

| Fixture | Status | What it shows |
| --- | --- | --- |
| `feedback_error_student_forbidden` | 403 | A student calling a staff endpoint: 403 forbidden. |

Error example (`feedback_error_student_forbidden`, 403):

```json
{
  "error": {
    "code": "forbidden",
    "message": "This role may not use this endpoint.",
    "details": {
      "role": "student"
    }
  }
}
```

**Errors**

| HTTP | Codes |
| --- | --- |
| 422 | `invalid_input`: Body, query or path failed validation, or the use case raised InvalidInput. |
| 403 | `forbidden`: The caller's role may not use this endpoint (or this office's resource). |
| 404 | `not_found`: The referenced request, prediction, ticket or incident does not exist. |
| 503 | `store_unavailable`: Supabase or the vector store is unreachable. |
| 401 | `unauthenticated`: Missing or wrong service token (or a bad webhook signature). |
| 500 | `internal_error`: Unexpected failure; no stack trace is returned. |

**Side effects**

- updates the prediction and its `review_queue` row; ticket `provisional` -> false
- inserts a `memory_examples` row (vector collection `memory`, active)
- fires deferred booking/alert actions (allow-listed email, `outbox` rows)
- appends an `events` row

<a id="ticket_status"></a>
## `POST /v1/tickets/{ticket_id}/status`

**Change a ticket's status from the dashboard.** Dashboard status change (LD-25); same path as the inbound Linear sync.

- **Roles:** `staff`, `admin`
- **Auth:** service token

**Parameters**

| Name | In | Type | Required | Notes |
| --- | --- | --- | --- | --- |
| `ticket_id` | path | string | yes |  |

Identity headers: `X-CP-User-JWT` (see [README › Auth](README.md#auth)).

**Request body**

`application/json`: [TicketStatusRequest](#schema-ticketstatusrequest)

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `status` | [TicketStatus](#schema-ticketstatus) | yes |  |
| `note` | string \| null | no |  |

**Response `200`:** `application/json` [TicketOut](#schema-ticketout)

**Example** (fixture `ticket_status_in_progress`): Staff move the safety ticket to in_progress from the dashboard.

`request.json`:

```json
{
  "status": "in_progress",
  "note": "Technician on the way."
}
```

```powershell
curl.exe -s -X POST "$env:AI_URL/v1/tickets/c1a9e3b7-2d4f-4e6a-9b8c-7d6e5f4a0003/status" `
  -H "Authorization: Bearer $env:AI_SERVICE_TOKEN" `
  -H "X-CP-User-JWT: $env:USER_JWT" `
  -H "Content-Type: application/json" `
  --data-binary "@request.json"
```

Response `200`:

```json
{
  "id": "c1a9e3b7-2d4f-4e6a-9b8c-7d6e5f4a0003",
  "request_id": "5b0e7c52-3f0a-4d8e-9c41-0a1b2c3d0003",
  "incident_id": null,
  "office": "Maintenance",
  "category": "Facilities",
  "priority": "high",
  "status": "in_progress",
  "provisional": false,
  "sla_due_at": "2026-11-06T09:14:00+03:00",
  "escalated_at": null,
  "resolved_at": null,
  "title": "Water leak next to power sockets in M 214",
  "links": [
    {
      "sink": "linear",
      "external_id": "CP-43",
      "url": "https://linear.app/campuspulse-demo/issue/CP-43"
    }
  ]
}
```

**Errors**

| HTTP | Codes |
| --- | --- |
| 422 | `invalid_input`: Body, query or path failed validation, or the use case raised InvalidInput. |
| 403 | `forbidden`: The caller's role may not use this endpoint (or this office's resource). |
| 404 | `not_found`: The referenced request, prediction, ticket or incident does not exist. |
| 503 | `store_unavailable`: Supabase or the vector store is unreachable. |
| 401 | `unauthenticated`: Missing or wrong service token (or a bad webhook signature). |
| 500 | `internal_error`: Unexpected failure; no stack trace is returned. |

**Side effects**

- updates the `tickets` row; updates the Linear issue
- in-app notification to the student; email on `resolved` if allow-listed

<a id="list_incidents"></a>
## `GET /v1/incidents`

**List incidents.** Pulse incidents, newest first; `?open=1` returns only open ones (LD-25).

- **Roles:** `staff`, `admin`, `service`
- **Auth:** service token

**Parameters**

| Name | In | Type | Required | Notes |
| --- | --- | --- | --- | --- |
| `open` | query | boolean \| null | no | `1` = only open incidents (LD-25). |

Identity headers: `X-CP-User-JWT` (see [README › Auth](README.md#auth)).

**Request body**

None.

**Response `200`:** `application/json` array of [IncidentOut](#schema-incidentout)

**Example** (fixture `incidents_open`): Open incidents (`?open=1`): one Wi-Fi outage in building M with 4 reports.

```powershell
curl.exe -s -X GET "$env:AI_URL/v1/incidents?open=1" `
  -H "Authorization: Bearer $env:AI_SERVICE_TOKEN" `
  -H "X-CP-User-JWT: $env:USER_JWT"
```

Response `200`:

```json
[
  {
    "id": "e4f2a6c8-1b3d-4f5e-8a7c-9b0d1e2f0001",
    "building": "M",
    "category": "IT Support",
    "title": "Wi-Fi outage in building M",
    "priority": "high",
    "report_count": 4,
    "status": "open",
    "member_ticket_ids": [
      "c1a9e3b7-2d4f-4e6a-9b8c-7d6e5f4a0011",
      "c1a9e3b7-2d4f-4e6a-9b8c-7d6e5f4a0012",
      "c1a9e3b7-2d4f-4e6a-9b8c-7d6e5f4a0013",
      "c1a9e3b7-2d4f-4e6a-9b8c-7d6e5f4a0014"
    ],
    "ticket_id": "c1a9e3b7-2d4f-4e6a-9b8c-7d6e5f4a0015",
    "opened_at": "2026-11-05T11:42:30+03:00",
    "resolved_at": null,
    "simulated": false
  }
]
```

**Errors**

| HTTP | Codes |
| --- | --- |
| 422 | `invalid_input`: Body, query or path failed validation, or the use case raised InvalidInput. |
| 403 | `forbidden`: The caller's role may not use this endpoint (or this office's resource). |
| 503 | `store_unavailable`: Supabase or the vector store is unreachable. |
| 401 | `unauthenticated`: Missing or wrong service token (or a bad webhook signature). |
| 500 | `internal_error`: Unexpected failure; no stack trace is returned. |

**Side effects**

- none (read-only)

<a id="resolve_incident"></a>
## `POST /v1/incidents/{incident_id}/resolve`

**Resolve an incident and notify reporters.** Closes the incident, its merged tickets and the Linear issue; notifies every reporter once.

- **Roles:** `staff`, `admin`
- **Auth:** service token

**Parameters**

| Name | In | Type | Required | Notes |
| --- | --- | --- | --- | --- |
| `incident_id` | path | string | yes |  |

Identity headers: `X-CP-User-JWT` (see [README › Auth](README.md#auth)).

**Request body**

`application/json`: [ResolveIncidentRequest](#schema-resolveincidentrequest)

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `note` | string \| null | no |  |

**Response `200`:** `application/json` [ResolveIncidentResponse](#schema-resolveincidentresponse)

**Example** (fixture `incident_resolve`): Staff resolve the Wi-Fi incident: member tickets close, 4 reporters are notified.

`request.json`:

```json
{
  "note": "The access point in M was replaced; Wi-Fi is back."
}
```

```powershell
curl.exe -s -X POST "$env:AI_URL/v1/incidents/e4f2a6c8-1b3d-4f5e-8a7c-9b0d1e2f0001/resolve" `
  -H "Authorization: Bearer $env:AI_SERVICE_TOKEN" `
  -H "X-CP-User-JWT: $env:USER_JWT" `
  -H "Content-Type: application/json" `
  --data-binary "@request.json"
```

Response `200`:

```json
{
  "incident": {
    "id": "e4f2a6c8-1b3d-4f5e-8a7c-9b0d1e2f0001",
    "building": "M",
    "category": "IT Support",
    "title": "Wi-Fi outage in building M",
    "priority": "high",
    "report_count": 4,
    "status": "resolved",
    "member_ticket_ids": [
      "c1a9e3b7-2d4f-4e6a-9b8c-7d6e5f4a0011",
      "c1a9e3b7-2d4f-4e6a-9b8c-7d6e5f4a0012",
      "c1a9e3b7-2d4f-4e6a-9b8c-7d6e5f4a0013",
      "c1a9e3b7-2d4f-4e6a-9b8c-7d6e5f4a0014"
    ],
    "ticket_id": "c1a9e3b7-2d4f-4e6a-9b8c-7d6e5f4a0015",
    "opened_at": "2026-11-05T11:42:30+03:00",
    "resolved_at": "2026-11-05T12:30:00+03:00",
    "simulated": false
  },
  "closed_ticket_ids": [
    "c1a9e3b7-2d4f-4e6a-9b8c-7d6e5f4a0011",
    "c1a9e3b7-2d4f-4e6a-9b8c-7d6e5f4a0012",
    "c1a9e3b7-2d4f-4e6a-9b8c-7d6e5f4a0013",
    "c1a9e3b7-2d4f-4e6a-9b8c-7d6e5f4a0014",
    "c1a9e3b7-2d4f-4e6a-9b8c-7d6e5f4a0015"
  ],
  "notified_reporters": 4
}
```

**More examples** (send `X-Mock-Fixture: <name>` to the mock app to get one)

| Fixture | Status | What it shows |
| --- | --- | --- |
| `incident_resolve_error_not_found` | 404 | Unknown incident id: 404 not_found. |

Error example (`incident_resolve_error_not_found`, 404):

```json
{
  "error": {
    "code": "not_found",
    "message": "Incident not found.",
    "details": {
      "incident_id": "00000000-0000-0000-0000-000000000000"
    }
  }
}
```

**Errors**

| HTTP | Codes |
| --- | --- |
| 422 | `invalid_input`: Body, query or path failed validation, or the use case raised InvalidInput. |
| 403 | `forbidden`: The caller's role may not use this endpoint (or this office's resource). |
| 404 | `not_found`: The referenced request, prediction, ticket or incident does not exist. |
| 503 | `store_unavailable`: Supabase or the vector store is unreachable. |
| 401 | `unauthenticated`: Missing or wrong service token (or a bad webhook signature). |
| 500 | `internal_error`: Unexpected failure; no stack trace is returned. |

**Side effects**

- updates `incidents` and the member `tickets` rows (status resolved/closed)
- closes the Linear issue
- one broadcast per reporter (in-app; email if allow-listed) -> `outbox` rows

<a id="insights_recurring"></a>
## `GET /v1/insights/recurring`

**Recurring problems.** Clusters stored request embeddings by meaning, building and category and ranks them by size, so staff can fix root causes (UD-6, P4.21).

- **Roles:** `staff`, `admin`
- **Auth:** service token

**Parameters**

| Name | In | Type | Required | Notes |
| --- | --- | --- | --- | --- |
| `window_days` | query | integer \| null | no | Null = all time. |
| `category` | query | [Category](#schema-category) \| null | no |  |
| `building` | query | string \| null | no |  |
| `top_k` | query | integer \| null | no | Null = `insights.top_k` (10). |

Identity headers: `X-CP-User-JWT` (see [README › Auth](README.md#auth)).

**Request body**

None.

**Response `200`:** `application/json` array of [ProblemClusterOut](#schema-problemclusterout)

**Example** (fixture `insights_recurring`): Top recurring problems over the last 30 days.

```powershell
curl.exe -s -X GET "$env:AI_URL/v1/insights/recurring?window_days=30&top_k=5" `
  -H "Authorization: Bearer $env:AI_SERVICE_TOKEN" `
  -H "X-CP-User-JWT: $env:USER_JWT"
```

Response `200`:

```json
[
  {
    "cluster_id": "cl-01",
    "category": "Facilities",
    "building_id": "H",
    "size": 7,
    "first_seen": "2026-10-14T09:10:00+03:00",
    "last_seen": "2026-11-04T15:22:00+03:00",
    "representative_text": "The projector in H 204 is not working again",
    "sample_request_ids": [
      "5b0e7c52-3f0a-4d8e-9c41-0a1b2c3d0101",
      "5b0e7c52-3f0a-4d8e-9c41-0a1b2c3d0102",
      "5b0e7c52-3f0a-4d8e-9c41-0a1b2c3d0103"
    ]
  },
  {
    "cluster_id": "cl-02",
    "category": "IT Support",
    "building_id": "M",
    "size": 5,
    "first_seen": "2026-10-20T10:00:00+03:00",
    "last_seen": "2026-11-05T11:42:30+03:00",
    "representative_text": "الواي فاي فاصل بمبنى M",
    "sample_request_ids": [
      "5b0e7c52-3f0a-4d8e-9c41-0a1b2c3d0104",
      "5b0e7c52-3f0a-4d8e-9c41-0a1b2c3d0105",
      "5b0e7c52-3f0a-4d8e-9c41-0a1b2c3d0106"
    ]
  },
  {
    "cluster_id": "cl-03",
    "category": "Transportation",
    "building_id": null,
    "size": 3,
    "first_seen": "2026-10-27T07:35:00+03:00",
    "last_seen": "2026-11-03T07:50:00+03:00",
    "representative_text": "The 7:15 bus from Madaba was late again",
    "sample_request_ids": [
      "5b0e7c52-3f0a-4d8e-9c41-0a1b2c3d0107",
      "5b0e7c52-3f0a-4d8e-9c41-0a1b2c3d0108",
      "5b0e7c52-3f0a-4d8e-9c41-0a1b2c3d0109"
    ]
  }
]
```

**Errors**

| HTTP | Codes |
| --- | --- |
| 422 | `invalid_input`: Body, query or path failed validation, or the use case raised InvalidInput. |
| 403 | `forbidden`: The caller's role may not use this endpoint (or this office's resource). |
| 503 | `store_unavailable`: Supabase or the vector store is unreachable. |
| 401 | `unauthenticated`: Missing or wrong service token (or a bad webhook signature). |
| 500 | `internal_error`: Unexpected failure; no stack trace is returned. |

**Side effects**

- none (read-only)

<a id="linear_webhook"></a>
## `POST /v1/integrations/linear/webhook`

**Inbound Linear status sync.** Receives Linear issue updates. The raw body is verified with HMAC-SHA256 (`LINEAR_WEBHOOK_SECRET`) against the `Linear-Signature` header; no service token.

- **Roles:** `public`
- **Auth:** HMAC signature (`Linear-Signature`)

**Parameters**

| Name | In | Type | Required | Notes |
| --- | --- | --- | --- | --- |
| `Linear-Signature` | header | string \| null | no |  |

**Request body**

`application/json`: object. Linear's webhook payload, verified byte-for-byte (not our schema).

**Response `200`:** `application/json` [WebhookAck](#schema-webhookack)

**Example** (fixture `linear_webhook_status_sync`): Linear moved CDP-43 to Done (`updatedFrom.stateId` marks a state change): the linked ticket becomes resolved.

`request.json`:

```json
{
  "action": "update",
  "type": "Issue",
  "data": {
    "id": "c1a9e3b7-2d4f-4e6a-9b8c-7d6e5f4a0003",
    "identifier": "CDP-43",
    "state": {
      "name": "Done",
      "type": "completed"
    }
  },
  "updatedFrom": {
    "stateId": "<previous state id>"
  },
  "webhookTimestamp": 1793858400000
}
```

```powershell
curl.exe -s -X POST "$env:AI_URL/v1/integrations/linear/webhook" `
  -H "Linear-Signature: <hex hmac-sha256 of the raw body>" `
  -H "Content-Type: application/json" `
  --data-binary "@request.json"
```

Response `200`:

```json
{
  "accepted": true,
  "ticket_id": "c1a9e3b7-2d4f-4e6a-9b8c-7d6e5f4a0003",
  "status": "resolved"
}
```

**More examples** (send `X-Mock-Fixture: <name>` to the mock app to get one)

| Fixture | Status | What it shows |
| --- | --- | --- |
| `linear_webhook_error_bad_signature` | 401 | Missing or wrong `Linear-Signature`: 401, nothing is written. |

Error example (`linear_webhook_error_bad_signature`, 401):

```json
{
  "error": {
    "code": "unauthenticated",
    "message": "Invalid webhook signature.",
    "details": null
  }
}
```

**Errors**

| HTTP | Codes |
| --- | --- |
| 401 | `unauthenticated`: Missing or wrong service token (or a bad webhook signature). |
| 422 | `invalid_input`: Body, query or path failed validation, or the use case raised InvalidInput. |
| 503 | `store_unavailable`: Supabase or the vector store is unreachable. |
| 500 | `internal_error`: Unexpected failure; no stack trace is returned. |

**Side effects**

- updates the linked `tickets` row status
- in-app notification to the student

<a id="batch"></a>
## `POST /v1/batch`

**Batch predictions from a CSV.** Upload a CSV with `request_id,text`; returns `request_id,category,priority` with the same bytes as `predict.py` (tier 0 by default).

- **Roles:** `staff`, `admin`
- **Auth:** service token

Identity headers: `X-CP-User-JWT` (see [README › Auth](README.md#auth)).

**Request body**

`multipart/form-data`: [Body_batch](#schema-body_batch)

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `file` | string | yes | CSV with columns request_id,text (UTF-8) |
| `use_llm` | boolean | no | default `false` |

**Response `200`:** `text/csv` string

**Example** (fixture `batch_csv`): Three rows through the tier-0 batch path (same bytes as predict.py).

`requests.csv`:

```csv
request_id,text
r-001,where is the bus timetable?
r-002,مش قادر أسجل مادة واليوم آخر يوم
r-003,the printer in the lab is not working
```

```powershell
curl.exe -s -X POST "$env:AI_URL/v1/batch" `
  -H "Authorization: Bearer $env:AI_SERVICE_TOKEN" `
  -H "X-CP-User-JWT: $env:USER_JWT" `
  -F "file=@requests.csv;type=text/csv" `
  -F "use_llm=false"
```

Response `200`:

```csv
request_id,category,priority
r-001,Transportation,low
r-002,Registration,high
r-003,IT Support,medium
```

**Errors**

| HTTP | Codes |
| --- | --- |
| 422 | `invalid_input`: Body, query or path failed validation, or the use case raised InvalidInput. |
| 403 | `forbidden`: The caller's role may not use this endpoint (or this office's resource). |
| 503 | `artifact_unavailable`: The frozen model artifact is missing or failed its checksum. |
| 401 | `unauthenticated`: Missing or wrong service token (or a bad webhook signature). |
| 500 | `internal_error`: Unexpected failure; no stack trace is returned. |

**Side effects**

- none (no rows written; LLM calls logged only with use_llm=true)

<a id="redteam_run"></a>
## `POST /v1/redteam/run`

**Run the red team.** Generates tricky requests per style, runs them through the real pipeline, scores them.

- **Roles:** `admin`
- **Auth:** service token

Identity headers: `X-CP-User-JWT` (see [README › Auth](README.md#auth)).

**Request body**

`application/json`: [RedTeamRunRequest](#schema-redteamrunrequest)

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `n` | integer | yes | >= 1.0 |
| `styles` | array of string \| null | no | Subset of: fake_urgency, calm_emergency, typos, arabizi, mixed_language, two_issues, very_long, injection, off_topic, distress_adjacent. Null = all |
| `seed` | integer | no | default `42` |

**Response `200`:** `application/json` [ScorecardOut](#schema-scorecardout)

**Example** (fixture `redteam_run`): Admin runs 20 red-team items over five styles.

`request.json`:

```json
{
  "n": 20,
  "styles": [
    "fake_urgency",
    "injection",
    "arabizi",
    "off_topic",
    "typos"
  ],
  "seed": 42
}
```

```powershell
curl.exe -s -X POST "$env:AI_URL/v1/redteam/run" `
  -H "Authorization: Bearer $env:AI_SERVICE_TOKEN" `
  -H "X-CP-User-JWT: $env:USER_JWT" `
  -H "Content-Type: application/json" `
  --data-binary "@request.json"
```

Response `200`:

```json
{
  "run_id": "rt-2026-11-05-01",
  "created_at": "2026-11-05T16:00:00+03:00",
  "n": 20,
  "seed": 42,
  "overall": 0.85,
  "by_style": {
    "fake_urgency": 1.0,
    "injection": 1.0,
    "arabizi": 0.67,
    "off_topic": 1.0,
    "typos": 0.67
  },
  "by_lang": {
    "en": 0.9,
    "ar": 0.8,
    "arabizi": 0.75
  },
  "failures": [
    {
      "text": "el printer bil lab 5arban mn embare7",
      "style": "arabizi",
      "lang": "arabizi",
      "intended_category": "Facilities",
      "intended_priority": "medium",
      "got_category": "IT Support",
      "got_priority": "medium",
      "outcome": "accept",
      "reason": "category IT Support != intended Facilities"
    },
    {
      "text": "my regstration wont go thru and its the last day",
      "style": "typos",
      "lang": "en",
      "intended_category": "Registration",
      "intended_priority": "high",
      "got_category": "Registration",
      "got_priority": "medium",
      "outcome": "accept",
      "reason": "priority medium != intended high"
    },
    {
      "text": "el bus ta5ar kteer el yom",
      "style": "arabizi",
      "lang": "arabizi",
      "intended_category": "Transportation",
      "intended_priority": "medium",
      "got_category": null,
      "got_priority": null,
      "outcome": "out_of_scope",
      "reason": "expected a decision, got out_of_scope"
    }
  ]
}
```

**Errors**

| HTTP | Codes |
| --- | --- |
| 422 | `invalid_input`: Body, query or path failed validation, or the use case raised InvalidInput. |
| 403 | `forbidden`: The caller's role may not use this endpoint (or this office's resource). |
| 503 | `artifact_unavailable`: The frozen model artifact is missing or failed its checksum. `store_unavailable`: Supabase or the vector store is unreachable. |
| 401 | `unauthenticated`: Missing or wrong service token (or a bad webhook signature). |
| 500 | `internal_error`: Unexpected failure; no stack trace is returned. |

**Side effects**

- inserts a `redteam_runs` row; no tickets, no notifications

<a id="metrics"></a>
## `GET /v1/metrics`

**Model lab metrics.** Benchmark, coverage, calibration, fairness, ablations, confusions, router/memory stats.

- **Roles:** `admin`
- **Auth:** service token

Identity headers: `X-CP-User-JWT` (see [README › Auth](README.md#auth)).

**Request body**

None.

**Response `200`:** `application/json` [MetricsResponse](#schema-metricsresponse)

**Example** (fixture `metrics`): Model-lab metrics (illustrative numbers, not real results).

```powershell
curl.exe -s -X GET "$env:AI_URL/v1/metrics" `
  -H "Authorization: Bearer $env:AI_SERVICE_TOKEN" `
  -H "X-CP-User-JWT: $env:USER_JWT"
```

Response `200`:

```json
{
  "artifact": {
    "version": "v1",
    "sha": "3f9a2c71b0d4"
  },
  "generated_at": "2026-11-04T22:10:00+03:00",
  "benchmark": [
    {
      "model": "M1",
      "target": "category",
      "dataset": "oof_official",
      "macro_f1": 0.81,
      "accuracy": 0.83,
      "n_rows": 432,
      "n_groups": 30,
      "status": "ok"
    },
    {
      "model": "M2-LR",
      "target": "category",
      "dataset": "oof_official",
      "macro_f1": 0.86,
      "accuracy": 0.87,
      "n_rows": 432,
      "n_groups": 30,
      "status": "ok"
    },
    {
      "model": "M2-kNN",
      "target": "category",
      "dataset": "oof_official",
      "macro_f1": 0.84,
      "accuracy": 0.85,
      "n_rows": 432,
      "n_groups": 30,
      "status": "ok"
    },
    {
      "model": "M3",
      "target": "category",
      "dataset": "oof_official",
      "macro_f1": null,
      "accuracy": null,
      "n_rows": 0,
      "n_groups": null,
      "status": "cut"
    },
    {
      "model": "Ensemble (tier 0)",
      "target": "category",
      "dataset": "our_test",
      "macro_f1": 0.88,
      "accuracy": 0.89,
      "n_rows": 64,
      "n_groups": 64,
      "status": "ok"
    },
    {
      "model": "Ensemble (tier 0)",
      "target": "priority",
      "dataset": "our_test",
      "macro_f1": 0.77,
      "accuracy": 0.8,
      "n_rows": 64,
      "n_groups": 64,
      "status": "ok"
    },
    {
      "model": "LLM zero-shot (M4)",
      "target": "category",
      "dataset": "our_test",
      "macro_f1": null,
      "accuracy": null,
      "n_rows": 64,
      "n_groups": 64,
      "status": "n/a"
    }
  ],
  "coverage": [
    {
      "target": "category",
      "dataset": "our_test",
      "lang": "all",
      "coverage": 0.92,
      "mean_set_size": 1.21,
      "singleton_rate": 0.81,
      "n_rows": 64,
      "n_groups": 64
    },
    {
      "target": "category",
      "dataset": "our_test",
      "lang": "ar",
      "coverage": 0.9,
      "mean_set_size": 1.28,
      "singleton_rate": 0.76,
      "n_rows": 25,
      "n_groups": 25
    }
  ],
  "ask_rate": 0.22,
  "ask_rate_is_proxy": true,
  "calibration": [
    {
      "target": "category",
      "ece": 0.041,
      "bins": [
        {
          "lower": 0.8,
          "upper": 0.9,
          "confidence": 0.85,
          "accuracy": 0.83,
          "count": 41
        },
        {
          "lower": 0.9,
          "upper": 1.0,
          "confidence": 0.95,
          "accuracy": 0.96,
          "count": 210
        }
      ]
    }
  ],
  "fairness": [
    {
      "slice": "en",
      "target": "category",
      "dataset": "our_test",
      "macro_f1": 0.9,
      "n_rows": 27,
      "n_groups": 27
    },
    {
      "slice": "ar",
      "target": "category",
      "dataset": "our_test",
      "macro_f1": 0.87,
      "n_rows": 25,
      "n_groups": 25
    },
    {
      "slice": "arabizi",
      "target": "category",
      "dataset": "our_test",
      "macro_f1": 0.82,
      "n_rows": 12,
      "n_groups": 12
    }
  ],
  "ablations": [
    {
      "arm": "no wrapper stripping",
      "target": "priority",
      "dataset": "oof_official",
      "macro_f1": 0.71,
      "delta": -0.05
    }
  ],
  "confusions": [
    {
      "model": "Ensemble (tier 0)",
      "target": "priority",
      "dataset": "our_test",
      "labels": [
        "low",
        "medium",
        "high"
      ],
      "matrix": [
        [
          18,
          3,
          0
        ],
        [
          2,
          17,
          3
        ],
        [
          0,
          4,
          17
        ]
      ]
    }
  ],
  "router": {
    "total": 128,
    "by_tier": {
      "tier0": 109,
      "tier1": 7,
      "human": 12
    },
    "resolved_tier0_pct": 85.2,
    "cost_usd": 0.0019,
    "cost_per_1k_usd": 0.0148,
    "cached_calls": 3
  },
  "memory": {
    "active": 4,
    "total": 5,
    "by_category": {
      "IT Support": 2,
      "Registration": 2
    },
    "last_added_at": "2026-11-05T10:58:12+03:00"
  },
  "redteam": [
    {
      "run_id": "rt-2026-11-05-01",
      "created_at": "2026-11-05T16:00:00+03:00",
      "n": 20,
      "seed": 42,
      "overall": 0.85,
      "by_style": {
        "fake_urgency": 1.0,
        "injection": 1.0,
        "arabizi": 0.67,
        "off_topic": 1.0,
        "typos": 0.67
      },
      "by_lang": {
        "en": 0.9,
        "ar": 0.8,
        "arabizi": 0.75
      },
      "failures": [
        {
          "text": "el printer bil lab 5arban mn embare7",
          "style": "arabizi",
          "lang": "arabizi",
          "intended_category": "Facilities",
          "intended_priority": "medium",
          "got_category": "IT Support",
          "got_priority": "medium",
          "outcome": "accept",
          "reason": "category IT Support != intended Facilities"
        },
        {
          "text": "my regstration wont go thru and its the last day",
          "style": "typos",
          "lang": "en",
          "intended_category": "Registration",
          "intended_priority": "high",
          "got_category": "Registration",
          "got_priority": "medium",
          "outcome": "accept",
          "reason": "priority medium != intended high"
        },
        {
          "text": "el bus ta5ar kteer el yom",
          "style": "arabizi",
          "lang": "arabizi",
          "intended_category": "Transportation",
          "intended_priority": "medium",
          "got_category": null,
          "got_priority": null,
          "outcome": "out_of_scope",
          "reason": "expected a decision, got out_of_scope"
        }
      ]
    }
  ]
}
```

**Errors**

| HTTP | Codes |
| --- | --- |
| 403 | `forbidden`: The caller's role may not use this endpoint (or this office's resource). |
| 503 | `store_unavailable`: Supabase or the vector store is unreachable. |
| 422 | `invalid_input`: Body, query or path failed validation, or the use case raised InvalidInput. |
| 401 | `unauthenticated`: Missing or wrong service token (or a bad webhook signature). |
| 500 | `internal_error`: Unexpected failure; no stack trace is returned. |

**Side effects**

- none (read-only)

<a id="health"></a>
## `GET /v1/health`

**Health.** Liveness, version, artifact hash, enabled sinks and LLM tiers. Also served at `/health`.

- **Roles:** `public`
- **Auth:** none

**Request body**

None.

**Response `200`:** `application/json` [HealthResponse](#schema-healthresponse)

**Example** (fixture `health`): Liveness and wiring of the deployed service.

```powershell
curl.exe -s -X GET "$env:AI_URL/v1/health"
```

Response `200`:

```json
{
  "status": "ok",
  "version": "0.1.0",
  "artifact": "v1",
  "sha": "3f9a2c71b0d4",
  "rss_mb": 318.4,
  "encoder_loaded": true,
  "sinks": [
    "supabase",
    "linear"
  ],
  "llm_tiers": [
    "tier1"
  ],
  "vector_store": "pgvector"
}
```

**Errors**

| HTTP | Codes |
| --- | --- |
| 500 | `internal_error`: Unexpected failure; no stack trace is returned. |

**Side effects**

- none

<a id="health_root"></a>
## `GET /health`

**Health (root alias).** Same as `/v1/health`; Render's health check path.

- **Roles:** `public`
- **Auth:** none

**Request body**

None.

**Response `200`:** `application/json` [HealthResponse](#schema-healthresponse)

**Example** (fixture `health`): Liveness and wiring of the deployed service.

```powershell
curl.exe -s -X GET "$env:AI_URL/v1/health"
```

Response `200`:

```json
{
  "status": "ok",
  "version": "0.1.0",
  "artifact": "v1",
  "sha": "3f9a2c71b0d4",
  "rss_mb": 318.4,
  "encoder_loaded": true,
  "sinks": [
    "supabase",
    "linear"
  ],
  "llm_tiers": [
    "tier1"
  ],
  "vector_store": "pgvector"
}
```

**Errors**

| HTTP | Codes |
| --- | --- |
| 500 | `internal_error`: Unexpected failure; no stack trace is returned. |

**Side effects**

- none

<a id="admin_simulate"></a>
## `POST /v1/admin/simulate`

**Start simulated Pulse traffic (optional extra).** Starts the scripted burst of `scripts/simulate_pulse.py` from the server (P5.19, B-list). **Optional extra (B-list): may return 501 when not built.**

- **Roles:** `admin`
- **Auth:** service token

Identity headers: `X-CP-User-JWT` (see [README › Auth](README.md#auth)).

**Request body**

`application/json`: [SimulateRequest](#schema-simulaterequest)

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `scenario` | string | no | A `config/simulation/<name>.yaml` scenario; default `"wifi_m"` |
| `interval_s` | number | no | default `4.0`; > 0.0 |

**Response `202`:** `application/json` [SimulateResponse](#schema-simulateresponse)

**Example** (fixture `admin_simulate`): Optional extra: start the Wi-Fi burst in building M from the server.

`request.json`:

```json
{
  "scenario": "wifi_m",
  "interval_s": 4.0
}
```

```powershell
curl.exe -s -X POST "$env:AI_URL/v1/admin/simulate" `
  -H "Authorization: Bearer $env:AI_SERVICE_TOKEN" `
  -H "X-CP-User-JWT: $env:USER_JWT" `
  -H "Content-Type: application/json" `
  --data-binary "@request.json"
```

Response `202`:

```json
{
  "run_id": "sim-2026-11-05-01",
  "scenario": "wifi_m",
  "queued": 8,
  "interval_s": 4.0,
  "label": "SIMULATED TRAFFIC"
}
```

**Errors**

| HTTP | Codes |
| --- | --- |
| 422 | `invalid_input`: Body, query or path failed validation, or the use case raised InvalidInput. |
| 403 | `forbidden`: The caller's role may not use this endpoint (or this office's resource). |
| 501 | `not_implemented`: Optional extra that is not built in this deployment. |
| 401 | `unauthenticated`: Missing or wrong service token (or a bad webhook signature). |
| 500 | `internal_error`: Unexpected failure; no stack trace is returned. |

**Side effects**

- posts each scenario line through /v1/triage with `simulated=true`

<a id="admin_reindex"></a>
## `POST /v1/admin/reindex`

**Re-embed a vector collection (optional extra).** Re-embeds the FAQ collection with the deployed encoder (P4.20, B-list). **Optional extra (B-list): may return 501 when not built.**

- **Roles:** `admin`
- **Auth:** service token

Identity headers: `X-CP-User-JWT` (see [README › Auth](README.md#auth)).

**Request body**

`application/json`: [ReindexRequest](#schema-reindexrequest)

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `collection` | `"faq"` | no | default `"faq"` |

**Response `200`:** `application/json` [ReindexResponse](#schema-reindexresponse)

**Example** (fixture `admin_reindex`): Optional extra: re-embed the FAQ collection.

`request.json`:

```json
{
  "collection": "faq"
}
```

```powershell
curl.exe -s -X POST "$env:AI_URL/v1/admin/reindex" `
  -H "Authorization: Bearer $env:AI_SERVICE_TOKEN" `
  -H "X-CP-User-JWT: $env:USER_JWT" `
  -H "Content-Type: application/json" `
  --data-binary "@request.json"
```

Response `200`:

```json
{
  "collection": "faq",
  "reindexed": 36,
  "dim": 384,
  "duration_ms": 2140
}
```

**More examples** (send `X-Mock-Fixture: <name>` to the mock app to get one)

| Fixture | Status | What it shows |
| --- | --- | --- |
| `admin_reindex_error_not_built` | 501 | Optional extra not built in this deployment: 501 not_implemented. |

Error example (`admin_reindex_error_not_built`, 501):

```json
{
  "error": {
    "code": "not_implemented",
    "message": "This optional endpoint is not built in this deployment.",
    "details": null
  }
}
```

**Errors**

| HTTP | Codes |
| --- | --- |
| 422 | `invalid_input`: Body, query or path failed validation, or the use case raised InvalidInput. |
| 403 | `forbidden`: The caller's role may not use this endpoint (or this office's resource). |
| 501 | `not_implemented`: Optional extra that is not built in this deployment. |
| 503 | `store_unavailable`: Supabase or the vector store is unreachable. |
| 401 | `unauthenticated`: Missing or wrong service token (or a bad webhook signature). |
| 500 | `internal_error`: Unexpected failure; no stack trace is returned. |

**Side effects**

- rewrites every `faq.embedding`

<a id="schemas"></a>
## Schemas

<a id="schema-ablationrowout"></a>
### AblationRowOut

One ablation arm (P2.9), scored on the same rows as the full system.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `arm` | string | yes |  |
| `target` | `category` \| `priority` | yes |  |
| `dataset` | `oof_official` \| `oof_all` \| `our_test` \| `our_test_set1` \| `our_test_set2` \| `our_test_set3` \| `probes` | yes |  |
| `macro_f1` | number \| null | yes | >= 0.0, <= 1.0 |
| `delta` | number \| null | yes | macro_f1 minus the full system's |

<a id="schema-actionout"></a>
### ActionOut

What happened next (SPEC §5.1 [11]).

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `type` | [ActionType](#schema-actiontype) | yes |  |
| `ticket_id` | string \| null | yes |  |
| `external` | array of [ExternalRefOut](#schema-externalrefout) | yes |  |
| `sla_due_at` | string (date-time) \| null | yes |  |
| `message` | string | yes | Student-facing sentence about the action |
| `provisional` | boolean | yes | True for `needs_review` items: ticket labelled unconfirmed |
| `tags` | array of string | yes | Ticket tags, e.g. `exam-in-progress` |
| `booking` | [BookingOut](#schema-bookingout) \| null | yes |  |
| `faq` | [FaqAnswerOut](#schema-faqanswerout) \| null | yes |  |
| `incident_id` | string \| null | yes | Set when the request was merged into an incident |

<a id="schema-actiontype"></a>
### ActionType

Values: `faq_answer`, `ticket`, `booking`, `safety_alert`, `incident_merge`

<a id="schema-artifactout"></a>
### ArtifactOut

The frozen model artifact in use.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `version` | string | yes |  |
| `sha` | string | yes |  |

<a id="schema-benchmarkrowout"></a>
### BenchmarkRowOut

One benchmark cell (SPEC §6.2). Null metrics = `n/a` (no key) or `cut` (M3).

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `model` | string | yes |  |
| `target` | `category` \| `priority` | yes |  |
| `dataset` | `oof_official` \| `oof_all` \| `our_test` \| `our_test_set1` \| `our_test_set2` \| `our_test_set3` \| `probes` | yes |  |
| `macro_f1` | number \| null | yes | >= 0.0, <= 1.0 |
| `accuracy` | number \| null | yes | >= 0.0, <= 1.0 |
| `n_rows` | integer | yes | >= 0.0 |
| `n_groups` | integer \| null | yes |  |
| `status` | `ok` \| `n/a` \| `cut` | yes |  |

<a id="schema-body_batch"></a>
### Body_batch

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `file` | string | yes | CSV with columns request_id,text (UTF-8) |
| `use_llm` | boolean | no | default `false` |

<a id="schema-bookingout"></a>
### BookingOut

An advisor slot booked for Academic Support x high (UD-1). Advisors are fictional.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `advisor_name` | string | yes |  |
| `starts_at` | string (date-time) | yes |  |
| `ends_at` | string (date-time) | yes |  |
| `room` | string \| null | yes |  |

<a id="schema-calibrationbinout"></a>
### CalibrationBinOut

One reliability-diagram bin.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `lower` | number | yes | >= 0.0, <= 1.0 |
| `upper` | number | yes | >= 0.0, <= 1.0 |
| `confidence` | number | yes | >= 0.0, <= 1.0 |
| `accuracy` | number | yes | >= 0.0, <= 1.0 |
| `count` | integer | yes | >= 0.0 |

<a id="schema-calibrationout"></a>
### CalibrationOut

Calibration of one target (ECE + reliability bins).

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `target` | `category` \| `priority` | yes |  |
| `ece` | number | yes | >= 0.0 |
| `bins` | array of [CalibrationBinOut](#schema-calibrationbinout) | yes |  |

<a id="schema-category"></a>
### Category

Values: `Registration`, `IT Support`, `Finance`, `Transportation`, `Facilities`, `Academic Support`

<a id="schema-categoryout"></a>
### CategoryOut

Category decision: the label, its probability and the conformal set.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `label` | [Category](#schema-category) | yes |  |
| `prob` | number | yes | >= 0.0, <= 1.0 |
| `set` | array of [Category](#schema-category) | yes | Conformal prediction set (1-alpha = 0.90) |

<a id="schema-clarificationoptionout"></a>
### ClarificationOptionOut

One answer chip.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | string | yes |  |
| `text` | string | yes |  |

<a id="schema-clarificationout"></a>
### ClarificationOut

The clarifying question asked when the request is ambiguous, in the request language.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `question_id` | string | yes | Question-bank id, e.g. `cat:Registration\|IT Support` |
| `text` | string | yes |  |
| `options` | array of [ClarificationOptionOut](#schema-clarificationoptionout) | yes |  |

<a id="schema-clarifyrequest"></a>
### ClarifyRequest

Body of `POST /v1/triage/{request_id}/clarify`: exactly one of `option_id` or `free_text`.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `question_id` | string | yes | min len 1 |
| `option_id` | string \| null | no |  |
| `free_text` | string \| null | no |  |

<a id="schema-confusionout"></a>
### ConfusionOut

A confusion matrix: rows = true label, columns = predicted, in `labels` order.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `model` | string | yes |  |
| `target` | `category` \| `priority` | yes |  |
| `dataset` | `oof_official` \| `oof_all` \| `our_test` \| `our_test_set1` \| `our_test_set2` \| `our_test_set3` \| `probes` | yes |  |
| `labels` | array of string | yes |  |
| `matrix` | array of array of integer | yes |  |

<a id="schema-counterfactualout"></a>
### CounterfactualOut

The smallest single-token deletion that flips category or priority.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `drop` | string | yes |  |
| `category` | [Category](#schema-category) | yes |  |
| `priority` | [Priority](#schema-priority) | yes |  |

<a id="schema-counterfactualresponse"></a>
### CounterfactualResponse

Live counterfactual: the labels the core gives with `drop` removed.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `request_id` | string | yes |  |
| `drop` | string | yes |  |
| `original_category` | [Category](#schema-category) | yes |  |
| `original_priority` | [Priority](#schema-priority) | yes |  |
| `category` | [Category](#schema-category) | yes |  |
| `priority` | [Priority](#schema-priority) | yes |  |
| `category_prob` | number | yes | >= 0.0, <= 1.0 |
| `priority_prob` | number | yes | >= 0.0, <= 1.0 |
| `flipped` | boolean | yes | True when category or priority changed |

<a id="schema-coveragerowout"></a>
### CoverageRowOut

Conformal coverage for one target/dataset/language slice (approximate; effective n ~ 30).

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `target` | `category` \| `priority` | yes |  |
| `dataset` | `oof_official` \| `oof_all` \| `our_test` \| `our_test_set1` \| `our_test_set2` \| `our_test_set3` \| `probes` | yes |  |
| `lang` | string | yes | `all`, `en`, `ar` or `arabizi` |
| `coverage` | number | yes | >= 0.0, <= 1.0 |
| `mean_set_size` | number | yes | >= 0.0 |
| `singleton_rate` | number | yes | >= 0.0, <= 1.0 |
| `n_rows` | integer | yes | >= 0.0 |
| `n_groups` | integer \| null | yes |  |

<a id="schema-entitiesout"></a>
### EntitiesOut

Entities extracted from the request (UD-10).

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `building` | string \| null | yes |  |
| `room` | string \| null | yes |  |
| `course_code` | string \| null | yes |  |
| `deadline` | string (date) \| null | yes |  |
| `system` | string \| null | yes |  |

<a id="schema-errorbody"></a>
### ErrorBody

The inside of every error response. `details` is free-form JSON (validation errors, request_id).

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `code` | [ErrorCode](#schema-errorcode) | yes |  |
| `message` | string | yes |  |
| `details` | object \| null | yes |  |

<a id="schema-errorcode"></a>
### ErrorCode

Machine-readable error codes. HTTP status per code is in `ERROR_HTTP_STATUS`.

Values: `invalid_input`, `unauthenticated`, `forbidden`, `not_found`, `clarification_budget_exceeded`, `not_implemented`, `artifact_unavailable`, `store_unavailable`, `internal_error`

<a id="schema-errorresponse"></a>
### ErrorResponse

Standard error body for every non-2xx response: `{"error": {"code", "message", "details"}}`.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `error` | [ErrorBody](#schema-errorbody) | yes |  |

<a id="schema-evidenceout"></a>
### EvidenceOut

An urgency evidence cue found in the text, e.g. `deadline_today` on `اليوم`.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `type` | string | yes | Evidence feature name (`EVIDENCE_FEATURES`, P1.12) |
| `span` | string | yes | The matched text span |

<a id="schema-explanationout"></a>
### ExplanationOut

Why the system decided what it did. Null when the explainer failed (flag `explanation_failed`).

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `top_tokens` | array of [string, number] | yes | [token, importance] pairs, top 5 |
| `neighbors` | array of [NeighborOut](#schema-neighborout) | yes |  |
| `counterfactual` | [CounterfactualOut](#schema-counterfactualout) \| null | yes |  |
| `trace` | [TraceOut](#schema-traceout) | yes |  |

<a id="schema-externalrefout"></a>
### ExternalRefOut

A ticket mirrored in an external sink (e.g. a Linear issue).

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `sink` | string | yes | Sink name, e.g. `linear` |
| `external_id` | string | yes |  |
| `url` | string \| null | yes |  |

<a id="schema-fairnesssliceout"></a>
### FairnessSliceOut

Macro-F1 on one language slice, with counts (LD-32, LD-33).

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `slice` | string | yes | `en`, `ar` or `arabizi` |
| `target` | `category` \| `priority` | yes |  |
| `dataset` | `oof_official` \| `oof_all` \| `our_test` \| `our_test_set1` \| `our_test_set2` \| `our_test_set3` \| `probes` | yes |  |
| `macro_f1` | number \| null | yes | >= 0.0, <= 1.0 |
| `n_rows` | integer | yes | >= 0.0 |
| `n_groups` | integer \| null | yes |  |

<a id="schema-faqanswerout"></a>
### FaqAnswerOut

A retrieved FAQ answer (never generated). `is_demo` marks placeholder entries.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `question` | string | yes |  |
| `answer` | string | yes |  |
| `source_url` | string | yes |  |
| `is_demo` | boolean | yes |  |
| `score` | number | yes | >= 0.0, <= 1.0 |

<a id="schema-feedbackrequest"></a>
### FeedbackRequest

Body of `POST /v1/feedback`: staff confirm (both null) or correct a prediction.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `prediction_id` | string | yes | min len 1 |
| `corrected_category` | [Category](#schema-category) \| null | no |  |
| `corrected_priority` | [Priority](#schema-priority) \| null | no |  |
| `note` | string | no | default `""` |

<a id="schema-feedbackresponse"></a>
### FeedbackResponse

Result of `POST /v1/feedback`.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `prediction_id` | string | yes |  |
| `request_id` | string | yes |  |
| `category` | [Category](#schema-category) | yes |  |
| `priority` | [Priority](#schema-priority) | yes |  |
| `tier` | [Tier](#schema-tier) | yes |  |
| `flags` | array of `distress` \| `empty_input` \| `empty_set` \| `explanation_failed` \| `gibberish` \| `injection_attempt` \| `llm_out_of_set` \| `needs_review` \| `out_of_scope` \| `priority_gaming_suspected` \| `safety` \| `staff_confirmed` \| `truncated` \| `understanding_fallback` \| `urgency_unsupported` | yes |  |
| `ticket` | [TicketOut](#schema-ticketout) \| null | yes |  |
| `memory` | [MemoryWriteOut](#schema-memorywriteout) | yes |  |
| `actions` | array of [ActionOut](#schema-actionout) | yes | Deferred actions that fired on confirmation |
| `message` | string | yes |  |

<a id="schema-healthresponse"></a>
### HealthResponse

`GET /health` (and `/v1/health`): liveness, artifact identity and wiring.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `status` | `ok` \| `degraded` | yes |  |
| `version` | string | yes | `campuspulse_ai.__version__` |
| `artifact` | string \| null | yes | Artifact version, e.g. `v1`; null before models exist |
| `sha` | string \| null | yes | `Manifest.sha` of the loaded artifact |
| `rss_mb` | number | yes |  |
| `encoder_loaded` | boolean | yes |  |
| `sinks` | array of string | yes |  |
| `llm_tiers` | array of [Tier](#schema-tier) | yes |  |
| `vector_store` | string \| null | yes |  |

<a id="schema-incidentout"></a>
### IncidentOut

A Pulse incident: several reports of the same problem in one building.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | string | yes |  |
| `building` | string | yes |  |
| `category` | [Category](#schema-category) | yes |  |
| `title` | string | yes |  |
| `priority` | [Priority](#schema-priority) | yes |  |
| `report_count` | integer | yes | >= 0.0 |
| `status` | `open` \| `resolved` | yes |  |
| `member_ticket_ids` | array of string | yes |  |
| `ticket_id` | string \| null | yes | The one incident ticket (linked to Linear) |
| `opened_at` | string (date-time) | yes |  |
| `resolved_at` | string (date-time) \| null | yes |  |
| `simulated` | boolean | no | True when every member report is `simulate_pulse.py` traffic (P4.10); default `false` |

<a id="schema-lang"></a>
### Lang

Values: `en`, `ar`, `arabizi`

<a id="schema-locationin"></a>
### LocationIn

A building (and optional room) the student picked on the map.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `building` | string | yes | Fictional building code, e.g. `M`; min len 1 |
| `room` | string \| null | no | Room code, e.g. `M 214` |

<a id="schema-memorystatsout"></a>
### MemoryStatsOut

Live memory stats (`MemoryStats`).

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `active` | integer | yes | >= 0.0 |
| `total` | integer | yes | >= 0.0 |
| `by_category` | object of integer | yes |  |
| `last_added_at` | string (date-time) \| null | yes |  |

<a id="schema-memorywriteout"></a>
### MemoryWriteOut

The live-memory example written by a staff correction.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `example_id` | string | yes |  |
| `active_examples` | integer | yes | Active memory size after the write; >= 0.0 |

<a id="schema-metricsresponse"></a>
### MetricsResponse

`GET /v1/metrics`: offline reports (`reports/*.json`) plus live router/memory/red-team stats.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `artifact` | [ArtifactOut](#schema-artifactout) | yes |  |
| `generated_at` | string (date-time) \| null | yes | When `evaluate.py` wrote the reports |
| `benchmark` | array of [BenchmarkRowOut](#schema-benchmarkrowout) | yes |  |
| `coverage` | array of [CoverageRowOut](#schema-coveragerowout) | yes |  |
| `ask_rate` | number \| null | yes | >= 0.0, <= 1.0 |
| `ask_rate_is_proxy` | boolean | yes | True while the rate is the P2 proxy (LD-24) |
| `calibration` | array of [CalibrationOut](#schema-calibrationout) | yes |  |
| `fairness` | array of [FairnessSliceOut](#schema-fairnesssliceout) | yes |  |
| `ablations` | array of [AblationRowOut](#schema-ablationrowout) | yes |  |
| `confusions` | array of [ConfusionOut](#schema-confusionout) | yes |  |
| `router` | [RouterStatsOut](#schema-routerstatsout) | yes |  |
| `memory` | [MemoryStatsOut](#schema-memorystatsout) | yes |  |
| `redteam` | array of [ScorecardOut](#schema-scorecardout) | yes |  |

<a id="schema-neighborout"></a>
### NeighborOut

A similar past example (training data or a staff correction in live memory).

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `text` | string | yes |  |
| `label` | [Category](#schema-category) | yes | The neighbour's category |
| `priority` | [Priority](#schema-priority) | yes |  |
| `sim` | number | yes | Cosine similarity to the request; >= 0.0, <= 1.0 |
| `source` | `train` \| `augmented` \| `memory` | yes |  |
| `created_at` | string (date-time) \| null | yes | Set for memory items ('learned N s ago') |

<a id="schema-outcome"></a>
### Outcome

Values: `accept`, `ask`, `escalate`, `human_review`, `out_of_scope`, `distress`

<a id="schema-priority"></a>
### Priority

Values: `low`, `medium`, `high`

<a id="schema-priorityout"></a>
### PriorityOut

Priority decision: label, probability, conformal set and the evidence that drove it.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `label` | [Priority](#schema-priority) | yes |  |
| `prob` | number | yes | >= 0.0, <= 1.0 |
| `set` | array of [Priority](#schema-priority) | yes |  |
| `evidence` | array of [EvidenceOut](#schema-evidenceout) | yes |  |

<a id="schema-problemclusterout"></a>
### ProblemClusterOut

A recurring problem (UD-6): semantically similar requests in one category/building.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `cluster_id` | string | yes |  |
| `category` | [Category](#schema-category) | yes |  |
| `building_id` | string \| null | yes |  |
| `size` | integer | yes | >= 1.0 |
| `first_seen` | string (date-time) | yes |  |
| `last_seen` | string (date-time) | yes |  |
| `representative_text` | string | yes |  |
| `sample_request_ids` | array of string | yes |  |

<a id="schema-redteamfailureout"></a>
### RedTeamFailureOut

A red-team item that failed its pass rule.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `text` | string | yes |  |
| `style` | string | yes |  |
| `lang` | [Lang](#schema-lang) | yes |  |
| `intended_category` | [Category](#schema-category) | yes |  |
| `intended_priority` | [Priority](#schema-priority) | yes |  |
| `got_category` | [Category](#schema-category) \| null | yes |  |
| `got_priority` | [Priority](#schema-priority) \| null | yes |  |
| `outcome` | [Outcome](#schema-outcome) | yes |  |
| `reason` | string | yes |  |

<a id="schema-redteamrunrequest"></a>
### RedTeamRunRequest

Body of `POST /v1/redteam/run`. `n` is capped by Settings `REDTEAM_MAX_N` (200).

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `n` | integer | yes | >= 1.0 |
| `styles` | array of string \| null | no | Subset of: fake_urgency, calm_emergency, typos, arabizi, mixed_language, two_issues, very_long, injection, off_topic, distress_adjacent. Null = all |
| `seed` | integer | no | default `42` |

<a id="schema-reindexrequest"></a>
### ReindexRequest

Body of `POST /v1/admin/reindex` (optional extra, P4.20).

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `collection` | `"faq"` | no | default `"faq"` |

<a id="schema-reindexresponse"></a>
### ReindexResponse

Result of re-embedding a vector collection.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `collection` | string | yes |  |
| `reindexed` | integer | yes | >= 0.0 |
| `dim` | integer | yes | >= 1.0 |
| `duration_ms` | integer | yes | >= 0.0 |

<a id="schema-resolveincidentrequest"></a>
### ResolveIncidentRequest

Body of `POST /v1/incidents/{incident_id}/resolve` (optional note to reporters).

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `note` | string \| null | no |  |

<a id="schema-resolveincidentresponse"></a>
### ResolveIncidentResponse

Result of resolving an incident.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `incident` | [IncidentOut](#schema-incidentout) | yes |  |
| `closed_ticket_ids` | array of string | yes |  |
| `notified_reporters` | integer | yes | >= 0.0 |

<a id="schema-routerstatsout"></a>
### RouterStatsOut

Live router stats (`RouterStats`).

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `total` | integer | yes | >= 0.0 |
| `by_tier` | object of integer | yes |  |
| `resolved_tier0_pct` | number | yes | >= 0.0, <= 100.0 |
| `cost_usd` | number | yes | >= 0.0 |
| `cost_per_1k_usd` | number | yes | >= 0.0 |
| `cached_calls` | integer | yes | >= 0.0 |

<a id="schema-scorecardout"></a>
### ScorecardOut

A red-team run's scorecard (pass rates in [0, 1]).

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `run_id` | string | yes |  |
| `created_at` | string (date-time) | yes |  |
| `n` | integer | yes | >= 0.0 |
| `seed` | integer | yes |  |
| `overall` | number | yes | >= 0.0, <= 1.0 |
| `by_style` | object of number | yes |  |
| `by_lang` | object of number | yes |  |
| `failures` | array of [RedTeamFailureOut](#schema-redteamfailureout) | yes |  |

<a id="schema-setsizesout"></a>
### SetSizesOut

Conformal set sizes.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `cat` | integer | yes | >= 0.0 |
| `pri` | integer | yes | >= 0.0 |

<a id="schema-simulaterequest"></a>
### SimulateRequest

Body of `POST /v1/admin/simulate` (optional extra, P5.19).

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `scenario` | string | no | A `config/simulation/<name>.yaml` scenario; default `"wifi_m"` |
| `interval_s` | number | no | default `4.0`; > 0.0 |

<a id="schema-simulateresponse"></a>
### SimulateResponse

A started simulated burst. All its requests carry `simulated=true`.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `run_id` | string | yes |  |
| `scenario` | string | yes |  |
| `queued` | integer | yes | >= 0.0 |
| `interval_s` | number | yes |  |
| `label` | `"SIMULATED TRAFFIC"` | yes |  |

<a id="schema-ticketout"></a>
### TicketOut

A CampusPulse ticket (system of record in Supabase).

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | string | yes |  |
| `request_id` | string | yes |  |
| `incident_id` | string \| null | yes |  |
| `office` | string | yes |  |
| `category` | [Category](#schema-category) | yes |  |
| `priority` | [Priority](#schema-priority) | yes |  |
| `status` | [TicketStatus](#schema-ticketstatus) | yes |  |
| `provisional` | boolean | yes |  |
| `sla_due_at` | string (date-time) | yes |  |
| `escalated_at` | string (date-time) \| null | yes |  |
| `resolved_at` | string (date-time) \| null | yes |  |
| `title` | string | yes |  |
| `links` | array of [ExternalRefOut](#schema-externalrefout) | yes |  |

<a id="schema-ticketstatus"></a>
### TicketStatus

Values: `open`, `in_progress`, `resolved`, `closed`, `escalated`, `merged`

<a id="schema-ticketstatusrequest"></a>
### TicketStatusRequest

Body of `POST /v1/tickets/{ticket_id}/status` (dashboard status change, LD-25).

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `status` | [TicketStatus](#schema-ticketstatus) | yes |  |
| `note` | string \| null | no |  |

<a id="schema-tier"></a>
### Tier

Values: `tier0`, `tier1`, `tier2`, `human`

<a id="schema-traceout"></a>
### TraceOut

Decision trace (SPEC §5.1 [10]).

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `sets` | [SetSizesOut](#schema-setsizesout) | yes |  |
| `models_agree` | boolean | yes |  |
| `cost_usd` | number | yes | >= 0.0 |
| `latency_ms` | integer | yes | >= 0.0 |
| `policy_path` | array of string | yes | DecisionPolicy rule ids in evaluation order, e.g. `a_gibberish`..`f_human` (P3.1) |
| `clarified` | boolean | yes | Whether a clarification answer was applied |
| `artifact_version` | string | yes |  |
| `per_model` | object of object of number \| null | yes | `<member>.<target>` -> {label: p}; only with `?debug=members` (admin, P5.16) |

<a id="schema-triagerequest"></a>
### TriageRequest

Body of `POST /v1/triage` (SPEC §7).

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `text` | string | yes | The student's message (or the confirmed voice transcript); min len 1 |
| `input_mode` | `text` \| `voice` | no | default `"text"` |
| `student_alias` | string | no | Pseudonymous alias such as `demo-17`; never a name; default `""` |
| `location` | [LocationIn](#schema-locationin) \| null | no |  |
| `conversation_id` | string \| null | no |  |
| `simulated` | boolean | no | True only for `scripts/simulate_pulse.py` traffic (P4.10); default `false` |

<a id="schema-triageresponse"></a>
### TriageResponse

Response of `POST /v1/triage` and `POST /v1/triage/{request_id}/clarify` (SPEC §7 + LD-25 + UD-10).  Which keys are null depends on `status` (docs/api/README.md › Status values).

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `request_id` | string | yes |  |
| `status` | `decided` \| `needs_clarification` \| `human_review` \| `out_of_scope` \| `distress` | yes |  |
| `lang` | [Lang](#schema-lang) | yes |  |
| `is_arabizi` | boolean | yes |  |
| `understood_as` | string \| null | yes | Arabic transliteration shown for Arabizi input (LD-25) |
| `category` | [CategoryOut](#schema-categoryout) \| null | yes |  |
| `priority` | [PriorityOut](#schema-priorityout) \| null | yes |  |
| `tier` | [Tier](#schema-tier) | yes |  |
| `clarification` | [ClarificationOut](#schema-clarificationout) \| null | yes |  |
| `explanation` | [ExplanationOut](#schema-explanationout) \| null | yes |  |
| `flags` | array of `distress` \| `empty_input` \| `empty_set` \| `explanation_failed` \| `gibberish` \| `injection_attempt` \| `llm_out_of_set` \| `needs_review` \| `out_of_scope` \| `priority_gaming_suspected` \| `safety` \| `staff_confirmed` \| `truncated` \| `understanding_fallback` \| `urgency_unsupported` | yes |  |
| `action` | [ActionOut](#schema-actionout) \| null | yes |  |
| `message` | string \| null | yes | Top-level student message (distress, out-of-scope, review) |
| `understanding` | [UnderstandingOut](#schema-understandingout) \| null | yes |  |

<a id="schema-understandingout"></a>
### UnderstandingOut

Structured understanding (UD-10). Never changes the decided labels.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `summary_en` | string | yes |  |
| `summary_ar` | string | yes |  |
| `entities` | [EntitiesOut](#schema-entitiesout) | yes |  |
| `student_reply` | string | yes |  |
| `ticket_title` | string | yes |  |
| `ticket_body` | string | yes |  |
| `source` | `llm` \| `rules` | yes |  |
| `prompt_version` | string \| null | yes |  |

<a id="schema-webhookack"></a>
### WebhookAck

Result of an inbound sink webhook. `accepted=false` = ignored event (not ours).

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `accepted` | boolean | yes |  |
| `ticket_id` | string \| null | yes |  |
| `status` | [TicketStatus](#schema-ticketstatus) \| null | yes |  |
