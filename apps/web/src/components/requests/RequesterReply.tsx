"use client";

import { useState, type FormEvent } from "react";
import { useT } from "@/i18n";
import { Button } from "../ui/Button";
import { TextArea } from "../ui/TextField";

/** Props for {@link RequesterReply}. */
export interface RequesterReplyProps {
  /** Sends the message; resolves true on success so the box clears itself. */
  onSend: (body: string) => Promise<boolean> | boolean;
  busy?: boolean;
  /** Show "Sending a message reopens your request" (a solved or closed ticket). */
  reopens?: boolean;
}

/** The requester's message box: a text area and Send. Never internal, never sets a status. */
export function RequesterReply({ onSend, busy = false, reopens = false }: RequesterReplyProps) {
  const t = useT();
  const [body, setBody] = useState("");
  const canSend = !busy && body.trim().length > 0;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!canSend) return;
    if ((await onSend(body.trim())) !== false) setBody("");
  };

  return (
    <form onSubmit={(e) => void submit(e)} aria-label={t("myRequests.reply.title")} className="flex flex-col gap-3">
      {reopens && <p className="text-sm text-fg-2">{t("myRequests.reply.reopens")}</p>}
      <TextArea label={t("myRequests.reply.label")} value={body} maxLength={4000} rows={4} disabled={busy} onChange={(e) => setBody(e.target.value)} />
      <div>
        <Button type="submit" loading={busy} disabled={!canSend}>
          {t("myRequests.reply.send")}
        </Button>
      </div>
    </form>
  );
}
