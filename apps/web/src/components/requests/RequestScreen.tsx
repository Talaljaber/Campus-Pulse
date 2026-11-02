"use client";

import { useFileOpener } from "@/hooks/useFileOpener";
import { useMyTicket } from "@/hooks/useMyTicket";
import { useLang, useT, type DictKey } from "@/i18n";
import type { AiFail } from "@/lib/ai/result";
import type { Role } from "@/lib/auth/routing";
import { ticketNumber } from "@/lib/tickets/number";
import { messageReopens, type StudentAction } from "@/lib/tickets/requester";
import { failMessage } from "@/lib/tickets/service";
import { formatDateTime } from "@/lib/time";
import { AppShell } from "../shell/AppShell";
import { PageHeader } from "../shell/PageHeader";
import { useOfficeLabel } from "../staff/office";
import { TicketThread } from "../tickets/TicketThread";
import { Badge } from "../ui/Badge";
import { Card } from "../ui/Card";
import { Loadable } from "../ui/Loadable";
import { useToast } from "../ui/Toast";
import { RequesterReply } from "./RequesterReply";
import { StudentActions } from "./StudentActions";

/** Props for {@link RequestScreen}. */
export interface RequestScreenProps {
  ticketId: string;
  role: Role;
  alias: string | null;
}

const ACTION_TOAST: Record<StudentAction, DictKey> = {
  solved: "myRequests.toast.solved",
  close: "myRequests.toast.close",
  keep_open: "myRequests.toast.keepOpen",
};

/** `/requests/[id]`: one of my own requests: the text, the department, the status, the thread, a message box and the answer buttons. */
export function RequestScreen({ ticketId, role, alias }: RequestScreenProps) {
  const t = useT();
  const { lang } = useLang();
  const toast = useToast();
  const officeLabel = useOfficeLabel();
  const thread = useMyTicket(ticketId, alias);
  const openFile = useFileOpener();
  const ticket = thread.ticket;
  const number = ticketNumber(ticketId);

  const settle = async (call: Promise<{ ok: true } | AiFail>, okMessage: string): Promise<boolean> => {
    const res = await call;
    if (res.ok) {
      toast.show(okMessage, "ok");
      return true;
    }
    const f = failMessage(res);
    toast.show(f.kind === "server" ? f.text : t(f.key), "danger");
    return false;
  };

  const crumbs = [
    { label: t("app.name"), href: "/" },
    { label: t("nav.requests"), href: "/requests" },
    { label: t("workspace.crumb", { number }) },
  ];

  return (
    <AppShell role={role} current="requests" alias={alias} crumbs={crumbs}>
      <Loadable state={thread.load === "notfound" ? "ready" : thread.load} onRetry={thread.reload}>
        {thread.load === "notfound" || !ticket ? (
          <p role="alert" className="rounded-lg border border-dashed border-line-strong p-6 text-center text-fg-2">
            {t("myRequests.notFound")}
          </p>
        ) : (
          <>
            <PageHeader
              title={t("workspace.title", { number })}
              subtitle={<span dir="auto">{ticket.title}</span>}
              badges={
                <>
                  <Badge tone="info" icon={null}>
                    {t(`staff.status.${ticket.status}` as DictKey)}
                  </Badge>
                  <Badge tone="info" icon={null}>
                    {officeLabel(ticket.office)}
                  </Badge>
                </>
              }
            />
            <div>
              <Badge tone="info" icon="info">
                {t("myRequests.demo")}
              </Badge>
            </div>
            {(ticket.status === "new" || ticket.status === "in_progress") && (
              <p className="text-sm text-fg-2">{t("myRequests.deadline", { when: formatDateTime(ticket.sla_due_at, lang) })}</p>
            )}
            <Card title={t("myRequests.yourRequest")}>
              <p dir="auto" className="whitespace-pre-wrap text-base text-fg-1">
                {ticket.body || ticket.title}
              </p>
            </Card>
            <Card title={t("workspace.thread")}>
              <div className="flex flex-col gap-4">
                <TicketThread activity={thread.activity} viewer="requester" files={thread.files} onOpenFile={openFile} />
                <StudentActions
                  ticket={ticket}
                  busy={thread.busy}
                  onAct={(action) => void settle(thread.act({ action }), t(ACTION_TOAST[action]))}
                />
                {ticket.status !== "merged" && (
                  <RequesterReply
                    busy={thread.busy}
                    reopens={messageReopens(ticket.status)}
                    files={thread.files}
                    onSend={(body, picked) => settle(picked ? thread.comment(body, picked) : thread.comment(body), t("myRequests.toast.sent"))}
                  />
                )}
              </div>
            </Card>
          </>
        )}
      </Loadable>
    </AppShell>
  );
}
