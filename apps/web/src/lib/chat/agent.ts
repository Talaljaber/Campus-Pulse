import { callAi } from "@/lib/ai/browser";
import type { AiResult } from "@/lib/ai/result";
import type { ChatConfirmResponse, ChatTurnResponse, ProposalOut, WireMessage } from "./agentTypes";

/** The service takes 1 to 20 messages of at most 2000 characters. */
export const MAX_TURN_MESSAGES = 20;
export const MAX_MESSAGE_CHARS = 2000;

/** Trims a conversation to what the service accepts: the latest 20 messages, each cut at 2000 characters. */
export function toWire(messages: readonly WireMessage[]): WireMessage[] {
  return messages.slice(-MAX_TURN_MESSAGES).map(({ role, content, kind }) => ({
    role,
    content: content.slice(0, MAX_MESSAGE_CHARS),
    ...(kind ? { kind } : {}),
  }));
}

/** `POST /v1/chat/turn`: one conversation turn. `token` is the pending proposal's token, if any. */
export function sendTurn(messages: readonly WireMessage[], token: string | null): Promise<AiResult<ChatTurnResponse>> {
  return callAi<ChatTurnResponse>("chat/turn", {
    method: "POST",
    body: { messages: toWire(messages), proposal_token: token },
  });
}

/** `POST /v1/chat/preview`: what would happen to this text, without creating anything. */
export function preview(text: string, asked: readonly string[], answer?: string | null): Promise<AiResult<ProposalOut>> {
  return callAi<ProposalOut>("chat/preview", {
    method: "POST",
    body: { text: text.slice(0, MAX_MESSAGE_CHARS), asked, ...(answer ? { answer } : {}) },
  });
}

/** `POST /v1/chat/confirm`: the student agreed; the service opens the request. */
export function confirm(token: string): Promise<AiResult<ChatConfirmResponse>> {
  return callAi<ChatConfirmResponse>("chat/confirm", { method: "POST", body: { proposal_token: token } });
}
