"use client";

import { useState } from "react";
import { useAdvisorReviews } from "@/hooks/useAdvisorReviews";
import { useFlagEvents } from "@/hooks/useFlagEvents";
import { useHints } from "@/hooks/useHints";
import { useNotifications } from "@/hooks/useNotifications";
import { useReviewQueue } from "@/hooks/useReviewQueue";
import { useT, type DictKey } from "@/i18n";
import type { Category, Priority, ReviewStatus } from "@/lib/ai/types";
import type { NoticeData } from "@/lib/chat/types";
import type { StaffErrorKind } from "@/lib/staff/service";
import { useNoticeText } from "../chat/ChatThread";
import { AppShell } from "../shell/AppShell";
import { PageHeader } from "../shell/PageHeader";
import { Badge } from "../ui/Badge";
import { Loadable } from "../ui/Loadable";
import { TabPanel, Tabs } from "../ui/Tabs";
import { useToast } from "../ui/Toast";
import { AdvisorReviewDetail, AdvisorReviewList } from "./AdvisorReviews";
import { FlagsPanel } from "./FlagsPanel";
import { useOfficeLabel } from "./office";
import { PastCorrections } from "./PastCorrections";
import { ReviewQueue } from "./ReviewQueue";

/** Props for {@link AdvisorScreen}. */
export interface AdvisorScreenProps {
  role: "staff" | "admin";
  alias?: string | null;
  office: string | null;
}

const STATUSES: readonly ReviewStatus[] = ["open", "confirmed", "corrected"];
const ID_BASE = "advisor";

/**
 * `/staff/reviews`: the advisor's review queue. Tabs pick open, confirmed or corrected items; the
 * list and the detail panel come from `GET /v1/reviews`. A `review_assigned` notification shows a
 * toast and re-reads the list.
 */
export function AdvisorScreen({ role, alias = null, office }: AdvisorScreenProps) {
  const t = useT();
  const toast = useToast();
  const noticeText = useNoticeText();
  const officeLabel = useOfficeLabel();
  const [status, setStatus] = useState<ReviewStatus>("open");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<{ id: string; kind: StaffErrorKind } | null>(null);
  const q = useAdvisorReviews(status);
  const flags = useFlagEvents();
  const past = useHints();
  const waiting = useReviewQueue();

  const onNotice = (n: NoticeData) => {
    if (n.type !== "review_assigned") return;
    toast.show(noticeText(n), "info");
    q.reload();
    waiting.reload();
  };
  useNotifications(alias, onNotice);
  useNotifications(office ? `office:${office}` : null, onNotice);

  const selected = q.items.find((i) => i.id === selectedId) ?? null;
  const errorText = selected && error?.id === selected.id ? t(`staff.error.${error.kind}` as DictKey) : null;

  const pick = (id: string | null) => {
    setError(null);
    setSelectedId(id);
  };
  const settle = (id: string, okMessage: DictKey) => (out: { ok: true } | { ok: false; kind: StaffErrorKind }) => {
    if (out.ok) toast.show(t(okMessage), "ok");
    else setError({ id, kind: out.kind });
  };

  const decide = async (run: () => ReturnType<typeof waiting.confirm>) => {
    const out = await run();
    if (out.ok) toast.show(t("staff.memoryToast"), "ok");
    else toast.show(t(`staff.error.${out.kind}` as DictKey), "danger");
  };

  return (
    <AppShell role={role} current="corrections" alias={alias}>
      <PageHeader
        title={t("advisor.title")}
        badges={
          <Badge tone="info" icon={null}>
            {office ? t("staff.office", { office: officeLabel(office) }) : t("staff.allOffices")}
          </Badge>
        }
      />
      <section aria-label={t("corrections.waitingSection")} className="flex flex-col gap-2">
        <h2 className="text-lg font-bold text-fg-1">{t("corrections.waitingSection")}</h2>
        <Loadable state={waiting.load} onRetry={waiting.reload}>
          <ReviewQueue
            items={waiting.items}
            pendingIds={waiting.pending}
            onConfirm={(pid) => void decide(() => waiting.confirm(pid))}
            onCorrect={(pid, category, priority, note) =>
              void decide(() =>
                waiting.correct(pid, {
                  category: (category as Category | undefined) ?? null,
                  priority: (priority as Priority | undefined) ?? null,
                  note: note ?? "",
                }),
              )
            }
          />
        </Loadable>
      </section>

      <Tabs
        items={STATUSES.map((s) => ({ id: s, label: t(`advisor.tabs.${s}` as DictKey) }))}
        value={status}
        onChange={(id) => {
          setStatus(id as ReviewStatus);
          pick(null);
        }}
        label={t("advisor.tabs.label")}
        idBase={ID_BASE}
      />
      {STATUSES.map((s) => (
        <TabPanel key={s} idBase={ID_BASE} id={s} value={status}>
          <Loadable state={q.load} onRetry={q.reload}>
            <div className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
              <section aria-label={t("advisor.listLabel")}>
                <AdvisorReviewList items={q.items} selectedId={selectedId} onSelect={pick} />
              </section>
              <aside aria-label={t("advisor.detail")}>
                {selected ? (
                  <AdvisorReviewDetail
                    item={selected}
                    busy={q.pending.has(selected.id)}
                    error={errorText}
                    onClose={() => pick(null)}
                    onConfirm={(item) => void q.confirm(item).then(settle(item.id, "staff.memoryToast"))}
                    onForward={(item, o, note) => void q.forward(item, o, note).then(settle(item.id, "advisor.forwarded"))}
                  />
                ) : (
                  <p className="rounded-lg border border-dashed border-line-strong p-6 text-center text-fg-2">{t("advisor.pick")}</p>
                )}
              </aside>
            </div>
          </Loadable>
        </TabPanel>
      ))}

      <section aria-label={t("corrections.flagsSection")}>
        <Loadable state={flags.load} onRetry={flags.reload}>
          <FlagsPanel events={flags.events} audience={role} />
        </Loadable>
      </section>

      <section aria-label={t("corrections.title")}>
        <Loadable state={past.load} onRetry={past.reload}>
          <PastCorrections hints={past.hints} />
        </Loadable>
      </section>
    </AppShell>
  );
}
