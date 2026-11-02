import type { components } from "@/lib/ai/types.gen";

/** Chat agent route types: aliases of the generated API types (`pnpm gen:types`), never hand-written. */
type S = components["schemas"];

export type WireMessage = S["ChatMessage"];
export type AgentRole = WireMessage["role"];
export type AgentKind = WireMessage["kind"];
export type ChatTurnRequest = S["ChatTurnRequest"];
export type ChatTurnResponse = S["ChatTurnResponse"];
export type AgentMode = ChatTurnResponse["mode"];
export type ChatPreviewRequest = S["ChatPreviewRequest"];
export type ProposalOut = S["ProposalOut"];
export type ProposalQuestion = S["ClarificationOut"];
export type ProposalQuestionOption = S["ClarificationOptionOut"];
export type ProposalHint = S["HintOut"];
export type ProposalWhy = S["ProposalWhyOut"];
export type ChatConfirmRequest = S["ChatConfirmRequest"];
export type ChatConfirmResponse = S["ChatConfirmResponse"];
export type ActionKind = S["ActionType"];
export type AgentPriority = S["Priority"];
