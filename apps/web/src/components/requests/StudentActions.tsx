"use client";

import { useState } from "react";
import { useT } from "@/i18n";
import { canCloseOwn, showStudentActions, type StudentAction } from "@/lib/tickets/requester";
import { Button } from "../ui/Button";

/** Props for {@link StudentActions}. */
export interface StudentActionsProps {
  ticket: { status: string; awaiting_student: boolean };
  busy?: boolean;
  onAct: (action: StudentAction) => void;
}

/** "Close this request" on a running request, with an "Are you sure?" step (P10.24). */
function CloseOwn({ busy, onClose }: { busy: boolean; onClose: () => void }) {
  const t = useT();
  const [asking, setAsking] = useState(false);
  if (!asking) {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm text-fg-2">{t("myRequests.actions.closeOwnHint")}</p>
        <Button variant="secondary" size="sm" disabled={busy} onClick={() => setAsking(true)}>
          {t("myRequests.actions.closeOwn")}
        </Button>
      </div>
    );
  }
  return (
    <div role="group" aria-label={t("myRequests.actions.closeOwn")} className="flex flex-col gap-2 rounded-md border border-line bg-surface-1 p-3">
      <p className="text-sm text-fg-1">{t("myRequests.actions.closeOwnConfirm")}</p>
      <div className="flex flex-wrap gap-2">
        <Button variant="danger" size="sm" disabled={busy} onClick={() => { setAsking(false); onClose(); }}>
          {t("myRequests.actions.closeOwnYes")}
        </Button>
        <Button variant="secondary" size="sm" disabled={busy} onClick={() => setAsking(false)}>
          {t("myRequests.actions.keepOpen")}
        </Button>
      </div>
    </div>
  );
}

/**
 * Solved / Close / Keep open while staff wait for the requester or once the ticket is solved; otherwise, on a
 * running request, "Close this request".
 */
export function StudentActions({ ticket, busy = false, onAct }: StudentActionsProps) {
  const t = useT();
  if (canCloseOwn(ticket)) return <CloseOwn busy={busy} onClose={() => onAct("close")} />;
  if (!showStudentActions(ticket)) return null;
  return (
    <div role="group" aria-label={t("myRequests.actions.title")} className="flex flex-col gap-2">
      <p className="text-sm text-fg-2">{t(ticket.status === "solved" ? "myRequests.actions.hintSolved" : "myRequests.actions.hintAwaiting")}</p>
      <div className="flex flex-wrap gap-2">
        <Button disabled={busy} onClick={() => onAct("solved")}>
          {t("myRequests.actions.solved")}
        </Button>
        <Button variant="secondary" disabled={busy} onClick={() => onAct("close")}>
          {t("myRequests.actions.close")}
        </Button>
        <Button variant="secondary" disabled={busy} onClick={() => onAct("keep_open")}>
          {t("myRequests.actions.keepOpen")}
        </Button>
      </div>
    </div>
  );
}
