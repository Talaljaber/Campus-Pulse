"use client";

import { useState, type FormEvent } from "react";
import { useT, type DictKey } from "@/i18n";
import type { StaffStatus } from "@/lib/tickets/transitions";
import type { FileRow } from "@/lib/files/types";
import type { CommentRequest } from "@/lib/tickets/types";
import { Button } from "../ui/Button";
import { FilePicker } from "./FilePicker";
import { Select } from "../ui/Select";
import { TextArea } from "../ui/TextField";

/** Props for {@link ReplyBox}. */
export interface ReplyBoxProps {
  /** Statuses the reply may set (from `staffStatusOptions`). Without any, the picker is hidden. */
  statusOptions: readonly StaffStatus[];
  /** Sends the comment (and the picked files, when there are any); resolves true on success so the box can clear itself. */
  onSend: (req: CommentRequest, files?: File[]) => Promise<boolean> | boolean | void;
  /** The ticket's current files. When given, the box offers an upload control; files follow the reply mode (internal note = staff only). */
  files?: readonly FileRow[];
  busy?: boolean;
  /** False when a public reply is not possible (a finished ticket: reopen it first). Only an internal note remains. */
  publicAllowed?: boolean;
}

type Mode = "public" | "internal";

/**
 * Staff reply: a text area, a switch between a public reply (the requester sees it and is emailed)
 * and an internal note (staff only), and an optional status to set with a public reply.
 */
export function ReplyBox({ statusOptions, onSend, files, busy = false, publicAllowed = true }: ReplyBoxProps) {
  const t = useT();
  const [body, setBody] = useState("");
  const [mode, setMode] = useState<Mode>("public");
  const [status, setStatus] = useState("");
  const [chosen, setChosen] = useState<File[]>([]);

  const internal = mode === "internal" || !publicAllowed;
  const options = statusOptions.filter((s): s is Exclude<StaffStatus, "new"> => s !== "new");
  const canSend = !busy && body.trim().length > 0;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!canSend) return;
    const picked = !internal && status !== "" ? (status as Exclude<StaffStatus, "new">) : null;
    const req = { body: body.trim(), internal, status: picked };
    const ok = await (files && chosen.length > 0 ? onSend(req, chosen) : onSend(req));
    if (ok !== false) {
      setBody("");
      setStatus("");
      setChosen([]);
    }
  };

  return (
    <form onSubmit={(e) => void submit(e)} aria-label={t("reply.title")} className="flex flex-col gap-3">
      <fieldset className="flex flex-wrap gap-x-5 gap-y-2" disabled={busy}>
        <legend className="mb-1 text-sm font-bold text-accent">{t("reply.mode")}</legend>
        {(["public", "internal"] as const).map((m) => (
          <label key={m} className="flex items-center gap-2 text-base text-fg-1">
            <input
              type="radio"
              name="reply-mode"
              value={m}
              checked={(m === "internal") === internal}
              disabled={m === "public" && !publicAllowed}
              onChange={() => setMode(m)}
              className="size-4 accent-[var(--cp-accent)]"
            />
            {t(`reply.${m}` as DictKey)}
          </label>
        ))}
      </fieldset>
      {!publicAllowed && <p className="text-sm text-fg-2">{t("reply.reopenHint")}</p>}
      <TextArea
        label={t(internal ? "reply.noteLabel" : "reply.replyLabel")}
        description={t(internal ? "reply.noteHint" : "reply.replyHint")}
        value={body}
        maxLength={4000}
        rows={4}
        disabled={busy}
        onChange={(e) => setBody(e.target.value)}
      />
      {files && <FilePicker picked={chosen} onChange={setChosen} existing={files} internal={internal} disabled={busy} />}
      {options.length > 0 && (
        <Select
          label={t("reply.status")}
          value={internal ? "" : status}
          disabled={busy || internal}
          onChange={(e) => setStatus(e.target.value)}
          options={[{ value: "", label: t("reply.statusKeep") }, ...options.map((s) => ({ value: s, label: t(`staff.status.${s}` as DictKey) }))]}
          className="max-w-72"
        />
      )}
      <div>
        <Button type="submit" loading={busy} disabled={!canSend}>
          {t(internal ? "reply.sendNote" : "reply.send")}
        </Button>
      </div>
    </form>
  );
}
