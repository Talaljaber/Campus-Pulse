/**
 * Real API example responses, imported from the backend's contract fixtures
 * (`services/ai/tests/fixtures/api/*.json`, validated against the DTOs by the
 * backend's own tests). Used by `/dev/ui` stories and component tests, never by pages.
 */
import ar_booking from "@fixtures/triage_decided_ar_booking.json";
import arabizi_exam from "@fixtures/triage_decided_arabizi_exam.json";
import en_faq from "@fixtures/triage_decided_en_faq.json";
import en_injection from "@fixtures/triage_decided_en_injection.json";
import en_safety from "@fixtures/triage_decided_en_safety.json";
import en_memory from "@fixtures/triage_decided_en_tier1_memory.json";
import distress_ar from "@fixtures/triage_distress_ar.json";
import human_review_en from "@fixtures/triage_human_review_en.json";
import clarification_ar from "@fixtures/triage_needs_clarification_ar.json";
import out_of_scope_en from "@fixtures/triage_out_of_scope_en.json";
import counterfactual from "@fixtures/counterfactual_drop_today.json";
import incidents from "@fixtures/incidents_open.json";
import type { CounterfactualView, Incident, TriageResponse } from "@/lib/ai/types";

interface TriageFixture {
  request: { text: string };
  response: unknown;
}

function triage(f: TriageFixture): { text: string; response: TriageResponse } {
  return { text: f.request.text, response: f.response as TriageResponse };
}

/** Every `/v1/triage` example, keyed by what it shows. Covers EN, AR and Arabizi, and all five statuses. */
export const TRIAGE_FIXTURES = {
  /** decided, EN, tier 1, a neighbour from live memory, a counterfactual */
  enMemory: triage(en_memory),
  /** decided, EN, FAQ answer */
  enFaq: triage(en_faq),
  /** decided, EN, injection flag */
  enInjection: triage(en_injection),
  /** decided, EN, safety alert */
  enSafety: triage(en_safety),
  /** decided, AR, advisor booking */
  arBooking: triage(ar_booking),
  /** decided, Arabizi, with the Arabic transliteration */
  arabiziExam: triage(arabizi_exam),
  /** needs_clarification, AR */
  arClarification: triage(clarification_ar),
  /** human_review, EN, provisional ticket */
  enHumanReview: triage(human_review_en),
  /** out_of_scope, EN */
  enOutOfScope: triage(out_of_scope_en),
  /** distress, AR */
  arDistress: triage(distress_ar),
} as const;

export type TriageFixtureName = keyof typeof TRIAGE_FIXTURES;

/** `GET /v1/explain/{id}/counterfactual` example (drops "اليوم"). */
export const COUNTERFACTUAL_FIXTURE = counterfactual.response as CounterfactualView;

/** `GET /v1/incidents` example. */
export const INCIDENT_FIXTURES = incidents.response as Incident[];
