import type { Category, TriageResponse } from "@/lib/ai/types";

/** Hand-written types of the chat agent routes (P9.8). The integrator may swap them for the generated ones. */
export type AgentRole = "user" | "assistant";
export type AgentKind = "text" | "proposal" | "ticket";
export type AgentPriority = "low" | "medium" | "high";
export type AgentMode = "llm" | "fallback";
export type ActionKind = "ticket" | "faq_answer" | "safety_alert";

/** One message as the service receives it. */
export interface WireMessage {
  role: AgentRole;
  content: string;
  kind?: AgentKind;
}

export interface ProposalQuestion {
  id: string;
  text: string;
  options: { id: string; label: string }[];
}

export interface ProposalOut {
  token: string;
  text: string;
  category: Category;
  priority: AgentPriority;
  office: string;
  action_kind: ActionKind;
  question: ProposalQuestion | null;
  faq: { question: string; answer: string } | null;
  hint: { category: Category; priority: string; similarity: number; text: string } | null;
  why: {
    category: { label: string; prob: number; set: Category[] };
    priority: { label: string; prob: number; set: string[] };
    neighbors: { text: string; sim: number; source: string }[];
  };
}

export interface ChatTurnResponse {
  mode: AgentMode;
  reply: string;
  proposal: ProposalOut | null;
  ticket_id: string | null;
  triage: TriageResponse | null;
  clear_proposal: boolean;
}

export interface ChatConfirmResponse {
  triage: TriageResponse;
  ticket_id: string | null;
  hint_applied: boolean;
}
