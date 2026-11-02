"use client";

import type { AiFail } from "@/lib/ai/result";
import { useT, type DictKey, labelOf, useLang } from "@/i18n";
import { useTicketDetail } from "@/hooks/useTicketDetail";
import { useFileOpener } from "@/hooks/useFileOpener";
import { useTicketThread } from "@/hooks/useTicketThread";
import { formatDateTime } from "@/lib/time";
import { isRunning, timeLeft } from "@/lib/tickets/clock";
import { ticketNumber } from "@/lib/tickets/number";
import { failMessage } from "@/lib/tickets/service";
import { staffStatusOptions } from "@/lib/tickets/transitions";
import { useNow } from "../explain/useNow";
import { AppShell } from "../shell/AppShell";
import { PageHeader } from "../shell/PageHeader";
import { ClockLabel } from "../tickets/ClockLabel";
import { PriorityBadge } from "../tickets/PriorityBadge";
import { ReplyBox } from "../tickets/ReplyBox";
import { TicketThread } from "../tickets/TicketThread";
import { Badge } from "../ui/Badge";
import { Card } from "../ui/Card";
import { Loadable } from "../ui/Loadable";
import { useToast } from "../ui/Toast";
import { useOfficeLabel } from "./office";
import { RequestPanel } from "./RequestPanel";
import { TicketSidePanel } from "./TicketSidePanel";

/** Props for {@link TicketWorkspace}. */
export interface TicketWorkspaceProps {
  ticketId: string;
  role: "staff" | "admin";
  alias: string | null;
}

/**
 * `/staff/tickets/[id]`: one ticket for staff. Header, the request and its decision, the thread with a
 * reply box, and a side panel to change status, forward and change priority. Reads go to Supabase under
 * row-level security; every write goes through the AI service, whose message is shown when it refuses.
 */
export function TicketWorkspace({ ticketId, role, alias }: TicketWorkspaceProps) {
  const t = useT();
  const { lang } = useLang();
  const toast = useToast();
  const officeLabel = useOfficeLabel();
  const clock = useNow();
  const thread = useTicketThread(ticketId, alias);
  const openFile = useFileOpener();
  const ticket = thread.ticket;
  const detail = useTicketDetail(ticket?.request_id ?? null);
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
    { label: t("app.name"), href: "/staff" },
    { label: t("nav.queue"), href: "/staff" },
    { label: t("workspace.crumb", { number }) },
  ];

  return (
    <AppShell role={role} current="queue" alias={alias} crumbs={crumbs}>
      <Loadable state={thread.load === "notfound" ? "ready" : thread.load} onRetry={thread.reload}>
        {thread.load === "notfound" || !ticket ? (
          <p role="alert" className="rounded-lg border border-dashed border-line-strong p-6 text-center text-fg-2">
            {t("workspace.notFound")}
          </p>
        ) : (
          <>
            <PageHeader
              title={t("workspace.title", { number })}
              subtitle={<span dir="auto">{ticket.title}</span>}
              badges={
                <>
                  <Badge tone={isRunning(ticket.status) ? "info" : "neutral"} icon={null}>
                    {t(`staff.status.${ticket.status}` as DictKey)}
                  </Badge>
                  <PriorityBadge priority={ticket.priority} />
                  <Badge tone="info" icon={null}>
                    {officeLabel(ticket.office)}
                  </Badge>
                  {clock !== null && timeLeft(ticket.sla_due_at, ticket.status, clock).state === "overdue" && <Badge tone="danger">{t("queue.overdue")}</Badge>}
                </>
              }
            />
            <p className="text-sm text-fg-2">
              {t("workspace.deadline", { when: formatDateTime(ticket.sla_due_at, lang) })} · {t("workspace.timeLeft")}:{" "}
              <ClockLabel dueIso={ticket.sla_due_at} status={ticket.status} now={clock} />
              {" · "}
              {labelOf("category", ticket.category, lang)}
            </p>
            <div className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
              <div className="flex flex-col gap-4">
                <Card title={t("workspace.request")}>
                  <RequestPanel
                    detail={detail.detail}
                    load={detail.load}
                    audience={role}
                    counterfactual={detail.counterfactual}
                    onCounterfactual={(token) => void detail.askCounterfactual(token)}
                  />
                </Card>
                <Card title={t("workspace.thread")}>
                  <div className="flex flex-col gap-4">
                    <TicketThread activity={thread.activity} viewer="staff" files={thread.files} onOpenFile={openFile} />
                    {ticket.status !== "merged" && (
                      <ReplyBox
                        busy={thread.busy}
                        statusOptions={staffStatusOptions(ticket.status)}
                        publicAllowed={isRunning(ticket.status)}
                        files={thread.files}
                        onSend={(req, picked) => settle(picked ? thread.comment(req, picked) : thread.comment(req), t(req.internal ? "reply.noteSaved" : "reply.sent"))}
                      />
                    )}
                  </div>
                </Card>
              </div>
              <aside aria-label={t("workspace.actions")}>
                <TicketSidePanel
                  ticket={ticket}
                  busy={thread.busy}
                  onStatus={(status, note) =>
                    settle(thread.changeStatus(status, note), t("staff.toast.statusChanged", { status: t(`staff.status.${status}` as DictKey) }))
                  }
                  onForward={(office, note) => settle(thread.forward(office, note), t("forward.toast", { office: officeLabel(office) }))}
                  onPriority={(priority, note) =>
                    settle(thread.changePriority(priority, note), t("workspace.priorityToast", { priority: labelOf("priority", priority, lang) }))
                  }
                />
              </aside>
            </div>
          </>
        )}
      </Loadable>
    </AppShell>
  );
}
