/**
 * Friendly aliases over the generated API types (`types.gen.ts`, produced from
 * `services/ai/openapi.json` by `pnpm gen:types`).
 *
 * Type-only on purpose: components import these as `import type`, so nothing from
 * this folder (in particular nothing server-only) reaches the client bundle. Field
 * names stay exactly as generated (snake_case, LD-36).
 */
import type { components } from "./types.gen";

type S = components["schemas"];

export type TriageResponse = S["TriageResponse"];
export type TriageStatus = TriageResponse["status"];
export type TriageFlag = TriageResponse["flags"][number];
/** Language the *service* detected for the input. The UI display language is `Lang` from `@/i18n`. */
export type InputLang = S["Lang"];
export type Tier = S["Tier"];
export type Category = S["Category"];
export type Priority = S["Priority"];

export type CategoryResult = S["CategoryOut"];
export type PriorityResult = S["PriorityOut"];
export type Evidence = S["EvidenceOut"];
/** `[token, weight]` pairs, heaviest first. */
export type TopToken = S["ExplanationOut"]["top_tokens"][number];

export type Explanation = S["ExplanationOut"];
export type Neighbor = S["NeighborOut"];
export type Trace = S["TraceOut"];
/** The counterfactual embedded in a triage response (`explanation.counterfactual`). */
export type CounterfactualHint = S["CounterfactualOut"];
/** The answer of `GET /v1/explain/{request_id}/counterfactual` (what the live click returns). */
export type CounterfactualView = S["CounterfactualResponse"];

export type Action = S["ActionOut"];
export type ActionType = S["ActionType"];
export type Booking = S["BookingOut"];
export type FaqAnswer = S["FaqAnswerOut"];
export type ExternalRef = S["ExternalRefOut"];

export type Clarification = S["ClarificationOut"];
export type Understanding = S["UnderstandingOut"];
export type Entities = S["EntitiesOut"];

export type Incident = S["IncidentOut"];
export type ErrorResponse = S["ErrorResponse"];
