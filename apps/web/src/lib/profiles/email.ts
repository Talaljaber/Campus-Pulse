import { callAi } from "@/lib/ai/browser";
import type { AiFail, AiResult } from "@/lib/ai/result";

export interface NotificationEmail {
  email: string | null;
  consented_at: string | null;
  opt_in_enabled: boolean;
}

export type EmailError = "session" | "invalid" | "limit" | "disabled" | "waking" | "generic";

export const getNotificationEmail = (): Promise<AiResult<NotificationEmail>> => callAi("profile/email");

export const saveNotificationEmail = (email: string, consent: boolean): Promise<AiResult<NotificationEmail>> =>
  callAi("profile/email", { method: "PUT", body: { email: email.trim(), consent } });

export const removeNotificationEmail = (): Promise<AiResult<NotificationEmail>> =>
  callAi("profile/email", { method: "DELETE" });

export function emailError(fail: AiFail): EmailError {
  if (fail.status === 401) return "session";
  if (fail.status === 422) return "invalid";
  if (fail.status === 429) return "limit";
  if (fail.status === 503 && !fail.waking) return "disabled";
  if (fail.waking) return "waking";
  return "generic";
}
