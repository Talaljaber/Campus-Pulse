"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import { useLang, useT, type DictKey } from "@/i18n";
import {
  PERIODS,
  alertsOf,
  daysUntil,
  duration,
  share,
  usd,
  type Alert,
  type LlmUsage,
  type OfficeStats,
  type Overview,
  type Period,
} from "@/lib/admin/overview";
import { useAiReading, type Remote } from "@/hooks/useAiReading";
import type { HealthResponse } from "@/lib/ai/types";
import { formatDateTime } from "@/lib/time";
import { AppShell } from "../shell/AppShell";
import { PageHeader } from "../shell/PageHeader";
import { useOfficeLabel } from "../staff/office";
import { Badge } from "../ui/Badge";
import { Card } from "../ui/Card";
import { DataTable, type Column, type SortState } from "../ui/DataTable";
import { Icon } from "../ui/Icon";
import { Select } from "../ui/Select";
import { Skeleton } from "../ui/Skeleton";

/** Props for {@link AdminOverview}. */
export interface AdminOverviewProps {
  alias: string | null;
  name?: string | null;
  period: Period;
  /** Null when the database could not be read. */
  overview: Overview | null;
}

/**
 * The admin home `/admin`: how the service is running across every office. Backlog and SLA, each
 * office's performance, request volume, how the AI handled requests, what the LLM costs, and whether
 * emails and ticket sync are getting through. Numbers come from `cp_admin_overview` (admin only);
 * spend comes from the AI service, which asks the LLM provider.
 */
export function AdminOverview({ alias, name = null, period, overview }: AdminOverviewProps) {
  const t = useT();
  const { lang } = useLang();
  const router = useRouter();
  const usage = useAiReading<LlmUsage>("admin/usage");
  const health = useAiReading<HealthResponse>("health");

  const onPeriod = useCallback((v: string) => router.push(`/admin?days=${v}`), [router]);

  return (
    <AppShell role="admin" current="overview" name={name} alias={alias}>
      <PageHeader title={t("admin.title")} subtitle={t("admin.subtitle")} />
      <div className="flex flex-wrap items-end justify-between gap-3">
        <Select
          label={t("admin.period.label")}
          value={String(period)}
          onChange={(e) => onPeriod(e.target.value)}
          options={PERIODS.map((p) => ({ value: String(p), label: t("admin.period.days", { days: p }) }))}
          className="w-48"
        />
        {overview && (
          <p className="text-sm text-fg-3">{t("admin.updated", { time: formatDateTime(overview.generated_at, lang) })}</p>
        )}
      </div>

      {overview === null ? (
        <div role="alert" className="rounded-lg border border-line-strong bg-surface-1 p-4">
          {t("admin.loadFailed")}
        </div>
      ) : (
        <>
          <Alerts alerts={alertsOf(overview, usage.state === "ready" ? usage.data : null)} />
          <Kpis o={overview} />
          <Offices rows={overview.offices} />
          <Volume o={overview} />
          <div className="grid gap-4 lg:grid-cols-2">
            <AiHandling o={overview} />
            <Spend usage={usage} />
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Delivery o={overview} health={health} />
            <People o={overview} />
          </div>
        </>
      )}
    </AppShell>
  );
}

function Alerts({ alerts }: { alerts: Alert[] }) {
  const t = useT();
  if (alerts.length === 0) {
    return (
      <p className="flex items-center gap-2 rounded-lg border border-line bg-surface-1 p-3 text-fg-2">
        <Icon name="check" size={18} className="text-ok" />
        {t("admin.alerts.none")}
      </p>
    );
  }
  return (
    <section aria-labelledby="admin-alerts" className="rounded-lg border border-line-strong border-s-[6px] border-s-orange bg-surface-1 p-4">
      <h2 id="admin-alerts" className="mb-2 font-bold">
        {t("admin.alerts.title")}
      </h2>
      <ul className="flex flex-col gap-1.5">
        {alerts.map((a) => (
          <li key={a.kind} className="flex items-start gap-2">
            <Icon name="alert" size={16} className="mt-1 shrink-0 text-danger" />
            <span>
              {t(`admin.alerts.${a.kind}` as DictKey, { count: a.count })}
              {a.href && (
                <>
                  {" "}
                  <Link href={a.href} className="font-medium text-accent underline underline-offset-2">
                    {t("admin.alerts.open")}
                  </Link>
                </>
              )}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Stat({ label, value, hint, tone }: { label: string; value: string; hint?: string; tone?: "danger" | "ok" }) {
  return (
    <div className="flex flex-col gap-1 rounded-lg border border-line bg-surface-1 p-4 shadow-1">
      <span className="text-sm text-fg-2">{label}</span>
      <span className={`text-2xl font-bold tabular-nums ${tone === "danger" ? "text-danger" : "text-fg-1"}`}>{value}</span>
      {hint && <span className="text-xs text-fg-3">{hint}</span>}
    </div>
  );
}

function useDuration(): (hours: number | null) => string {
  const t = useT();
  return (hours) => {
    const d = duration(hours);
    return d ? t(`admin.unit.${d.unit}` as DictKey, { value: d.value }) : t("common.none");
  };
}

function Kpis({ o }: { o: Overview }) {
  const t = useT();
  const dur = useDuration();
  const dash = t("common.none");
  return (
    <section aria-label={t("admin.kpi.label")} className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
      <Stat label={t("admin.kpi.requests")} value={String(o.requests.total)} hint={t("admin.kpi.students", { count: o.requests.students })} />
      <Stat label={t("admin.kpi.open")} value={String(o.tickets.open)} hint={t("admin.kpi.received", { count: o.tickets.received })} />
      <Stat label={t("admin.kpi.overdue")} value={String(o.tickets.overdue)} tone={o.tickets.overdue > 0 ? "danger" : undefined} />
      <Stat label={t("admin.kpi.highOpen")} value={String(o.tickets.high_open)} tone={o.tickets.high_open > 0 ? "danger" : undefined} />
      <Stat label={t("admin.kpi.median")} value={dur(o.tickets.median_hours)} hint={t("admin.kpi.resolved", { count: o.tickets.resolved })} />
      <Stat label={t("admin.kpi.sla")} value={o.tickets.sla_met_pct === null ? dash : `${o.tickets.sla_met_pct}%`} hint={t("admin.kpi.slaHint")} />
    </section>
  );
}

function Offices({ rows }: { rows: OfficeStats[] }) {
  const t = useT();
  const officeLabel = useOfficeLabel();
  const dur = useDuration();
  const dash = t("common.none");
  const [sort, setSort] = useState<SortState>({ columnId: "open", dir: "desc" });
  const num = (n: number, danger = false) => <span className={`tabular-nums ${danger && n > 0 ? "font-bold text-danger" : ""}`}>{n}</span>;
  const columns: Column<OfficeStats>[] = [
    { id: "office", primary: true, header: t("admin.offices.office"), cell: (r) => officeLabel(r.office), sortValue: (r) => officeLabel(r.office) },
    { id: "open", primary: true, header: t("admin.offices.open"), cell: (r) => num(r.open), sortValue: (r) => r.open },
    { id: "overdue", header: t("admin.offices.overdue"), cell: (r) => num(r.overdue, true), sortValue: (r) => r.overdue },
    { id: "high", header: t("admin.offices.high"), cell: (r) => num(r.high_open, true), sortValue: (r) => r.high_open },
    { id: "received", header: t("admin.offices.received"), cell: (r) => num(r.received), sortValue: (r) => r.received },
    { id: "resolved", header: t("admin.offices.resolved"), cell: (r) => num(r.resolved), sortValue: (r) => r.resolved },
    { id: "median", header: t("admin.offices.median"), cell: (r) => dur(r.median_hours), sortValue: (r) => r.median_hours ?? -1 },
    {
      id: "sla",
      header: t("admin.offices.sla"),
      cell: (r) => (r.sla_met_pct === null ? dash : `${r.sla_met_pct}%`),
      sortValue: (r) => r.sla_met_pct ?? -1,
    },
  ];
  return (
    <Card title={t("admin.offices.title")}>
      <DataTable caption={t("admin.offices.caption")} columns={columns} rows={rows} rowKey={(r) => r.office} sort={sort} onSortChange={setSort} empty={dash} />
    </Card>
  );
}

function Volume({ o }: { o: Overview }) {
  const t = useT();
  const { lang } = useLang();
  const max = Math.max(1, ...o.daily.map((d) => d.requests));
  const dayLabel = (iso: string) =>
    new Date(`${iso}T12:00:00Z`).toLocaleDateString(lang === "ar" ? "ar-JO" : "en-GB", { day: "numeric", month: "short" });
  const first = o.daily[0];
  const last = o.daily[o.daily.length - 1];
  const langs = o.requests.by_lang;
  const total = Math.max(1, langs.en + langs.ar + langs.arabizi);
  return (
    <Card title={t("admin.volume.title")}>
      <div className="flex flex-col gap-4">
        <figure className="flex flex-col gap-2">
          <div className="flex h-36 items-end gap-0.5" role="img" aria-label={t("admin.volume.chartLabel", { total: o.requests.total, days: o.days })}>
            {o.daily.map((d) => (
              <div key={d.day} className="group relative flex h-full flex-1 items-end" title={`${dayLabel(d.day)}: ${d.requests}`}>
                <div
                  className="w-full rounded-t-[4px] bg-accent transition-opacity group-hover:opacity-80"
                  style={{ height: d.requests === 0 ? "1px" : `${(100 * d.requests) / max}%`, opacity: d.requests === 0 ? 0.35 : undefined }}
                />
              </div>
            ))}
          </div>
          {first && last && (
            <figcaption className="flex justify-between text-xs text-fg-3">
              <span>{dayLabel(first.day)}</span>
              <span>{t("admin.volume.peak", { count: max === 1 && o.requests.total === 0 ? 0 : max })}</span>
              <span>{dayLabel(last.day)}</span>
            </figcaption>
          )}
        </figure>
        <div className="flex flex-col gap-2">
          <h4 className="text-sm font-bold text-fg-2">{t("admin.volume.languages")}</h4>
          {(["en", "ar", "arabizi"] as const).map((k) => (
            <div key={k} className="grid grid-cols-[6rem_1fr_3.5rem] items-center gap-2 text-sm">
              <span>{t(`admin.lang.${k}` as DictKey)}</span>
              <span className="h-2 overflow-hidden rounded-full bg-surface-2">
                <span className="block h-full rounded-full bg-accent" style={{ width: `${(100 * langs[k]) / total}%` }} />
              </span>
              <span className="text-end tabular-nums text-fg-2">{langs[k]}</span>
            </div>
          ))}
          <p className="text-sm text-fg-2">
            {t("admin.volume.extra", { voice: o.requests.voice, distress: o.requests.distress, out: o.requests.out_of_scope })}
          </p>
        </div>
      </div>
    </Card>
  );
}

function Row({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-line py-2 last:border-b-0">
      <dt className="text-fg-2">
        {label}
        {hint && <span className="block text-xs text-fg-3">{hint}</span>}
      </dt>
      <dd className="font-bold tabular-nums">{value}</dd>
    </div>
  );
}

function AiHandling({ o }: { o: Overview }) {
  const t = useT();
  const dash = t("common.none");
  const pct = (n: number | null) => (n === null ? dash : `${n}%`);
  const reviewed = o.ai.corrected + o.ai.confirmed;
  return (
    <Card title={t("admin.ai.title")}>
      <dl>
        <Row label={t("admin.ai.classified")} value={String(o.ai.classified)} />
        <Row label={t("admin.ai.automatic")} value={pct(share(o.ai.automatic, o.ai.classified))} hint={t("admin.ai.automaticHint")} />
        <Row label={t("admin.ai.toHuman")} value={pct(share(o.ai.to_human, o.ai.classified))} hint={t("admin.ai.toHumanHint")} />
        <Row label={t("admin.ai.asked")} value={String(o.ai.asked_question)} />
        <Row
          label={t("admin.ai.corrected")}
          value={pct(share(o.ai.corrected, reviewed))}
          hint={t("admin.ai.correctedHint", { corrected: o.ai.corrected, reviewed })}
        />
        <Row label={t("admin.ai.reviewsOpen")} value={String(o.ai.reviews_open)} />
      </dl>
      <Link href="/staff/reviews" className="mt-3 inline-block text-sm font-medium text-accent underline underline-offset-2">
        {t("admin.ai.openReviews")}
      </Link>
    </Card>
  );
}

function Spend({ usage }: { usage: Remote<LlmUsage> }) {
  const t = useT();
  const { lang } = useLang();
  const dash = t("common.none");
  if (usage.state === "loading") {
    return (
      <Card title={t("admin.spend.title")}>
        <Skeleton lines={5} />
      </Card>
    );
  }
  if (usage.state === "error" || !usage.data.available) {
    return (
      <Card title={t("admin.spend.title")}>
        <p className="text-fg-2">{t("admin.spend.unavailable")}</p>
      </Card>
    );
  }
  const u = usage.data;
  const used = u.limit_usd !== null && u.limit_remaining_usd !== null ? u.limit_usd - u.limit_remaining_usd : null;
  const usedPct = used !== null && u.limit_usd ? Math.min(100, (100 * used) / u.limit_usd) : null;
  const expires = daysUntil(u.key_expires_at);
  return (
    <Card title={t("admin.spend.title")}>
      <dl>
        <Row label={t("admin.spend.today")} value={usd(u.spent_today_usd) ?? dash} />
        <Row label={t("admin.spend.week")} value={usd(u.spent_week_usd) ?? dash} />
        <Row label={t("admin.spend.month")} value={usd(u.spent_month_usd) ?? dash} />
        <Row label={t("admin.spend.total")} value={usd(u.spent_total_usd) ?? dash} />
      </dl>
      {usedPct !== null && u.limit_usd !== null && (
        <div className="mt-3 flex flex-col gap-1">
          <div className="flex justify-between text-sm">
            <span className="text-fg-2">
              {t(u.limit_reset ? "admin.spend.limitReset" : "admin.spend.limit", {
                limit: usd(u.limit_usd) ?? dash,
                reset: u.limit_reset ? t(`admin.spend.reset.${u.limit_reset}` as DictKey) : "",
              })}
            </span>
            <span className="tabular-nums">{t("admin.spend.left", { left: usd(u.limit_remaining_usd) ?? dash })}</span>
          </div>
          <span className="h-2 overflow-hidden rounded-full bg-surface-2" role="img" aria-label={t("admin.spend.used", { pct: Math.round(usedPct) })}>
            <span className={`block h-full rounded-full ${usedPct >= 80 ? "bg-danger" : "bg-accent"}`} style={{ width: `${usedPct}%` }} />
          </span>
        </div>
      )}
      <p className="mt-3 text-sm text-fg-2">
        {expires === null ? t("admin.spend.noExpiry") : t("admin.spend.expires", { date: formatDateTime(u.key_expires_at ?? "", lang), days: expires })}
      </p>
      <p className="mt-1 text-xs text-fg-3">{t("admin.spend.models", { models: u.models.join(", ") || dash })}</p>
    </Card>
  );
}

function Delivery({ o, health }: { o: Overview; health: Remote<HealthResponse> }) {
  const t = useT();
  const d = o.delivery;
  const service =
    health.state === "loading" ? (
      <Badge tone="neutral">{t("common.loading")}</Badge>
    ) : health.state === "ready" && health.data.status === "ok" ? (
      <Badge tone="ok" icon="check">
        {t("admin.delivery.online")}
      </Badge>
    ) : (
      <Badge tone="danger" icon="alert">
        {t("admin.delivery.offline")}
      </Badge>
    );
  return (
    <Card title={t("admin.delivery.title")}>
      <dl>
        <div className="flex items-center justify-between gap-3 border-b border-line py-2">
          <dt className="text-fg-2">
            {t("admin.delivery.service")}
            {health.state === "ready" && health.data.artifact && (
              <span className="block text-xs text-fg-3">
                {t("admin.delivery.model", { version: health.data.artifact, sha: (health.data.sha ?? "").slice(0, 7) })}
              </span>
            )}
          </dt>
          <dd>{service}</dd>
        </div>
        <Row label={t("admin.delivery.sent")} value={String(d.sent)} />
        <Row label={t("admin.delivery.failed")} value={String(d.failed)} />
        <Row label={t("admin.delivery.rejected")} value={String(d.rejected)} hint={t("admin.delivery.rejectedHint")} />
        <Row label={t("admin.delivery.queued")} value={String(d.queued)} />
        <Row label={t("admin.delivery.synced")} value={String(d.synced)} hint={t("admin.delivery.syncErrors", { count: d.sync_errors })} />
      </dl>
      <Link href="/outbox" className="mt-3 inline-block text-sm font-medium text-accent underline underline-offset-2">
        {t("admin.delivery.openOutbox")}
      </Link>
    </Card>
  );
}

function People({ o }: { o: Overview }) {
  const t = useT();
  return (
    <Card title={t("admin.people.title")}>
      <dl>
        <Row label={t("admin.people.students")} value={String(o.people.students)} hint={t("admin.people.active", { count: o.requests.students })} />
        <Row label={t("admin.people.staff")} value={String(o.people.staff)} />
        <Row label={t("admin.people.admins")} value={String(o.people.admins)} />
        <Row label={t("admin.people.incidents")} value={String(o.incidents.open)} hint={t("admin.people.incidentsOpened", { count: o.incidents.opened })} />
      </dl>
      <div className="mt-3 flex flex-wrap gap-4 text-sm">
        <Link href="/admin/accounts" className="font-medium text-accent underline underline-offset-2">
          {t("admin.people.openAccounts")}
        </Link>
        <Link href="/pulse" className="font-medium text-accent underline underline-offset-2">
          {t("admin.people.openIncidents")}
        </Link>
      </div>
    </Card>
  );
}
