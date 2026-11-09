"use client";

import { useState } from "react";
import { useAnnouncementDrafts, type DraftOutcome } from "@/hooks/useAnnouncementDrafts";
import { useT } from "@/i18n";
import { DRAFT_BODY_MAX, DRAFT_TITLE_MAX, type AnnouncementDraft } from "@/lib/announcements/drafts";
import { useOfficeLabel } from "../staff/office";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { Dialog } from "../ui/Dialog";
import { useToast } from "../ui/Toast";
import { TextArea, TextField } from "../ui/TextField";

type Action = "publish" | "save" | "dismiss";

/** One pending draft: editable title and text, with Publish, Save changes and Dismiss. */
function DraftCard({
  draft,
  onResult,
  actions,
}: {
  draft: AnnouncementDraft;
  onResult: (outcome: DraftOutcome, done: "published" | "saved" | "dismissed") => void;
  actions: ReturnType<typeof useAnnouncementDrafts>;
}) {
  const t = useT();
  const officeLabel = useOfficeLabel();
  const [title, setTitle] = useState(draft.title);
  const [body, setBody] = useState(draft.body);
  const [busy, setBusy] = useState<Action | null>(null);
  const [confirming, setConfirming] = useState(false);

  const valid = title.trim().length > 0 && title.trim().length <= DRAFT_TITLE_MAX && body.trim().length > 0 && body.trim().length <= DRAFT_BODY_MAX;
  const changed = title.trim() !== draft.title || body.trim() !== draft.body;

  const run = async (action: Action) => {
    if (busy) return;
    setBusy(action);
    let outcome: DraftOutcome;
    if (action === "publish") outcome = await actions.publish(draft, title, body);
    else if (action === "save") outcome = await actions.edit(draft, title, body);
    else outcome = await actions.dismiss(draft);
    setBusy(null);
    setConfirming(false);
    onResult(outcome, action === "publish" ? "published" : action === "save" ? "saved" : "dismissed");
  };

  return (
    <li>
      <Card className="flex flex-col gap-3">
        <p className="text-sm text-fg-2">{t("announcements.drafts.office", { office: officeLabel(draft.office) })}</p>
        <TextField
          label={t("announcements.drafts.titleField")}
          value={title}
          maxLength={DRAFT_TITLE_MAX}
          onChange={(e) => setTitle(e.target.value)}
          dir="auto"
        />
        <TextArea label={t("announcements.drafts.bodyField")} value={body} maxLength={DRAFT_BODY_MAX} onChange={(e) => setBody(e.target.value)} dir="auto" />
        <div className="flex flex-wrap gap-2">
          <Button disabled={!valid || busy !== null} loading={busy === "publish"} onClick={() => void run("publish")}>
            {t("announcements.drafts.publish")}
          </Button>
          <Button variant="secondary" disabled={!valid || !changed || busy !== null} loading={busy === "save"} onClick={() => void run("save")}>
            {t("announcements.drafts.save")}
          </Button>
          <Button variant="secondary" disabled={busy !== null} onClick={() => setConfirming(true)}>
            {t("announcements.drafts.dismiss")}
          </Button>
        </div>
        <Dialog open={confirming} onClose={() => busy === null && setConfirming(false)} title={t("announcements.drafts.dismissTitle")}>
          <p dir="auto">{t("announcements.drafts.dismissBody", { title: draft.title })}</p>
          <div className="mt-4 flex flex-wrap justify-end gap-2">
            <Button variant="secondary" disabled={busy !== null} onClick={() => setConfirming(false)}>
              {t("common.cancel")}
            </Button>
            <Button variant="danger" loading={busy === "dismiss"} onClick={() => void run("dismiss")}>
              {t("announcements.drafts.dismiss")}
            </Button>
          </div>
        </Dialog>
      </Card>
    </li>
  );
}

/** "Suggested from incidents": pending announcement drafts for staff to review. Renders nothing when there are none. */
export function SuggestedDrafts() {
  const t = useT();
  const toast = useToast();
  const actions = useAnnouncementDrafts();

  if (actions.drafts.length === 0) return null;

  const onResult = (outcome: DraftOutcome, done: "published" | "saved" | "dismissed") => {
    if (outcome === "ok") toast.show(t(`announcements.drafts.${done}`), "ok");
    else toast.show(t(outcome === "conflict" ? "announcements.drafts.conflict" : "announcements.drafts.failed"), "danger");
  };

  return (
    <section aria-labelledby="suggested-drafts-title" className="flex flex-col gap-3">
      <h2 id="suggested-drafts-title" className="text-lg font-bold">
        {t("announcements.drafts.title")}
      </h2>
      <p className="text-fg-2">{t("announcements.drafts.hint")}</p>
      <ul className="flex flex-col gap-3">
        {actions.drafts.map((d) => (
          <DraftCard key={d.id} draft={d} actions={actions} onResult={onResult} />
        ))}
      </ul>
    </section>
  );
}
