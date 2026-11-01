"use client";

import { useState } from "react";
import { useFlagEvents } from "@/hooks/useFlagEvents";
import { useIncidents } from "@/hooks/useIncidents";
import { useMapBuildings } from "@/hooks/useMapBuildings";
import { useNotifications } from "@/hooks/useNotifications";
import { useReviewQueue } from "@/hooks/useReviewQueue";
import { useTicketDetail } from "@/hooks/useTicketDetail";
import { useTicketQueue } from "@/hooks/useTicketQueue";
import { useT, type DictKey } from "@/i18n";
import type { Category, Priority } from "@/lib/ai/types";
import type { NoticeData } from "@/lib/chat/types";
import { incidentView } from "@/lib/incidents";
import type { StaffErrorKind } from "@/lib/staff/service";
import { filterTickets, type QueueFilter } from "@/lib/staff/tickets";
import { useNoticeText } from "../chat/ChatThread";
import { useNow } from "../explain/useNow";
import { AppShell } from "../shell/AppShell";
import { PageHeader } from "../shell/PageHeader";
import { Badge } from "../ui/Badge";
import { Loadable } from "../ui/Loadable";
import { Select } from "../ui/Select";
import { TabPanel, Tabs } from "../ui/Tabs";
import { useToast } from "../ui/Toast";
import { FlagsPanel } from "./FlagsPanel";
import { IncidentsPanel } from "./IncidentsPanel";
import { useOfficeLabel } from "./office";
import { RequestDetail } from "./RequestDetail";
import { ReviewQueue } from "./ReviewQueue";
import { TicketQueue } from "./TicketQueue";

/** Props for {@link StaffScreen}. */
export interface StaffScreenProps {
  role: "staff" | "admin";
  /** The signed-in user's alias, for the header greeting. */
  alias?: string | null;
  /** The staff member's office code (D-005). Null for an admin, who sees every office. */
  office: string | null;
}

const TAB_IDS = ["tickets", "review", "incidents", "flags"] as const;
type TabId = (typeof TAB_IDS)[number];
const ID_BASE = "staff";

/**
 * The staff dashboard `/staff`: the office's ticket queue with request details, the human
 * review queue (confirm or correct), open incidents and flagged requests. It only wires the
 * data hooks to presentational components. Which rows appear is decided by row-level security
 * in the database, never by filtering here.
 */
export function StaffScreen({ role, alias = null, office }: StaffScreenProps) {
  const t = useT();
  const toast = useToast();
  const officeLabel = useOfficeLabel();
  const clock = useNow();
  const now = new Date(clock ?? 0);

  const queue = useTicketQueue(office);
  const review = useReviewQueue();
  const incidents = useIncidents();
  const flags = useFlagEvents();
  const buildings = useMapBuildings();

  // UD-13: a ticket forwarded to this office, and an item landing in the advisor's or the office's review queue.
  const noticeText = useNoticeText();
  const onNotice = (n: NoticeData) => {
    if (n.type === "ticket_forwarded" || n.type === "review_assigned") toast.show(noticeText(n), "info");
    if (n.type === "review_assigned") review.reload();
  };
  useNotifications(alias, onNotice);
  useNotifications(office ? `office:${office}` : null, onNotice);

  const [tab, setTab] = useState<TabId>("tickets");
  const [filter, setFilter] = useState<QueueFilter>("active");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const selected = queue.tickets.find((x) => x.id === selectedId) ?? null;
  const detail = useTicketDetail(selected?.request_id ?? null);

  const fail = (kind: StaffErrorKind) => toast.show(t(`staff.error.${kind}` as DictKey), "danger");

  const onStatus = async (id: string, status: Parameters<typeof queue.changeStatus>[1]) => {
    const kind = await queue.changeStatus(id, status);
    if (kind) fail(kind);
    else toast.show(t("staff.toast.statusChanged", { status: t(`staff.status.${status}` as DictKey) }), "ok");
  };

  const [forwardError, setForwardError] = useState<{ id: string; kind: StaffErrorKind } | null>(null);
  const onForward = async (id: string, to: string, note: string) => {
    setForwardError(null);
    const kind = await queue.forward(id, to, note);
    if (kind) setForwardError({ id, kind });
    else toast.show(t("forward.toast", { office: officeLabel(to) }), "ok");
  };

  const decide = async (run: () => ReturnType<typeof review.confirm>) => {
    const out = await run();
    if (!out.ok) fail(out.kind);
    else toast.show(t("staff.memoryToast"), "ok");
  };

  const onResolve = async (id: string, note?: string) => {
    const out = await incidents.resolve(id, note);
    if (!out.ok) fail(out.kind);
    else toast.show(t("staff.toast.incidentResolved", { count: out.notified }), "ok");
  };

  const incidentViews = incidents.rows.map(incidentView);
  const items = TAB_IDS.map((id) => ({
    id,
    label:
      id === "review"
        ? t("staff.tabs.review", { count: review.items.length })
        : id === "incidents"
          ? t("staff.tabs.incidents", { count: incidents.rows.length })
          : t(`staff.tabs.${id}` as DictKey),
  }));

  return (
    <AppShell role={role} current="staff" alias={alias}>
      <PageHeader
        title={t("staff.title")}
        badges={
          <Badge tone="info" icon={null}>
            {office ? t("staff.office", { office: officeLabel(office) }) : t("staff.allOffices")}
          </Badge>
        }
      />

      <Tabs items={items} value={tab} onChange={(id) => setTab(id as TabId)} label={t("staff.tabs.label")} idBase={ID_BASE} />

      <TabPanel idBase={ID_BASE} id="tickets" value={tab}>
        <div className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
          <section aria-label={t("staff.queue.title")} className="flex flex-col gap-3">
            <Select
              label={t("staff.queue.filterLabel")}
              value={filter}
              onChange={(e) => setFilter(e.target.value as QueueFilter)}
              options={[
                { value: "active", label: t("staff.queue.filterActive") },
                { value: "done", label: t("staff.queue.filterDone") },
                { value: "all", label: t("staff.queue.filterAll") },
              ]}
              className="max-w-48"
            />
            <Loadable state={queue.load} onRetry={queue.reload}>
              <TicketQueue
                tickets={filterTickets(queue.tickets, filter)}
                now={now}
                onStatus={(id, s) => void onStatus(id, s)}
                onSelect={setSelectedId}
                selectedId={selectedId}
                pendingIds={queue.pending}
                showOffice={office === null}
              />
            </Loadable>
          </section>
          <aside aria-label={t("staff.detail.title")}>
            {selected ? (
              <RequestDetail
                key={`${selected.id}:${selected.office}`}
                ticket={selected}
                onForward={(to, note) => void onForward(selected.id, to, note)}
                forwardBusy={queue.pending.has(selected.id)}
                forwardError={forwardError?.id === selected.id ? t(`staff.error.${forwardError.kind}` as DictKey) : null}
                detail={detail.detail}
                load={detail.load}
                audience={role}
                counterfactual={detail.counterfactual}
                onCounterfactual={(token) => void detail.askCounterfactual(token)}
                onClose={() => setSelectedId(null)}
              />
            ) : (
              <p className="rounded-lg border border-dashed border-line-strong p-6 text-center text-fg-2">{t("staff.detail.empty")}</p>
            )}
          </aside>
        </div>
      </TabPanel>

      <TabPanel idBase={ID_BASE} id="review" value={tab}>
        <Loadable state={review.load} onRetry={review.reload}>
          <ReviewQueue
            items={review.items}
            pendingIds={review.pending}
            onConfirm={(pid) => void decide(() => review.confirm(pid))}
            onCorrect={(pid, category, priority, note) =>
              void decide(() =>
                review.correct(pid, {
                  category: (category as Category | undefined) ?? null,
                  priority: (priority as Priority | undefined) ?? null,
                  note: note ?? "",
                }),
              )
            }
          />
        </Loadable>
      </TabPanel>

      <TabPanel idBase={ID_BASE} id="incidents" value={tab}>
        <Loadable state={incidents.load} onRetry={incidents.reload}>
          <IncidentsPanel incidents={incidentViews} buildings={buildings} onResolve={onResolve} />
        </Loadable>
      </TabPanel>

      <TabPanel idBase={ID_BASE} id="flags" value={tab}>
        <Loadable state={flags.load} onRetry={flags.reload}>
          <FlagsPanel events={flags.events} audience={role} />
        </Loadable>
      </TabPanel>
    </AppShell>
  );
}
