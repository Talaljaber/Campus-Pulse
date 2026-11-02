"use client";

import { useT } from "@/i18n";
import { showStudentActions, type StudentAction } from "@/lib/tickets/requester";
import { Button } from "../ui/Button";

/** Props for {@link StudentActions}. */
export interface StudentActionsProps {
  ticket: { status: string; awaiting_student: boolean };
  busy?: boolean;
  onAct: (action: StudentAction) => void;
}

/** Solved / Close / Keep open: shown while staff wait for the requester, or once the ticket is solved. */
export function StudentActions({ ticket, busy = false, onAct }: StudentActionsProps) {
  const t = useT();
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
