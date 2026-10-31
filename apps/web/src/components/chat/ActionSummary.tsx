"use client";

import { useId, type ReactNode } from "react";
import { useLang, useT } from "@/i18n";
import type { Action, ExternalRef, TriageStatus } from "@/lib/ai/types";
import { Badge } from "../ui/Badge";
import { cn } from "../ui/cn";
import { textDir } from "../explain/text";

/** Props for {@link ActionSummary}. */
export interface ActionSummaryProps {
  /** `result.action`. `null` renders nothing (clarification, out of scope, distress). */
  action: Action | null;
  /** `result.status`. A `human_review` result explains that booking and alerts wait for staff. */
  status: TriageStatus;
  className?: string;
}

/** Only web links are rendered as anchors, so a bad `url` can never become `javascript:`. */
function safeHref(url: string | null): string | null {
  return url && /^https?:\/\//i.test(url) ? url : null;
}

function Row({ children }: { children: ReactNode }) {
  return <p className="text-sm text-fg-2">{children}</p>;
}

function ExternalLink({ r, label }: { r: ExternalRef; label: string }) {
  const href = safeHref(r.url);
  return href ? (
    <a href={href} target="_blank" rel="noreferrer noopener" className="font-medium text-accent underline underline-offset-2">
      {label}
    </a>
  ) : (
    <span className="font-medium text-fg-1">{r.external_id}</span>
  );
}

/**
 * "What happens next": the ticket with its Linear link and SLA, the advisor booking
 * time, the FAQ answer with its source (and a demo marker), or the safety alert,
 * depending on `action.type`. Every sentence comes from the dictionaries; only the
 * data (ids, names, times, FAQ text) comes from the API.
 */
export function ActionSummary({ action, status, className }: ActionSummaryProps) {
  const t = useT();
  const { lang } = useLang();
  const titleId = useId();
  if (!action) return null;

  const locale = lang === "ar" ? "ar-JO-u-nu-latn" : "en-GB";
  const dateTime = new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Amman" });
  const timeOnly = new Intl.DateTimeFormat(locale, { timeStyle: "short", timeZone: "Asia/Amman" });
  const fmt = (iso: string) => dateTime.format(new Date(iso));

  const showTicket =
    action.type !== "faq_answer" && (action.type === "ticket" || action.ticket_id !== null || action.external.length > 0);
  const deferred = status === "human_review" && action.type !== "safety_alert";

  return (
    <section
      aria-labelledby={titleId}
      data-action={action.type}
      className={cn("flex flex-col gap-3 rounded-lg border border-line bg-surface-1 p-4", className)}
    >
      <h3 id={titleId} className="text-md font-semibold text-fg-1">
        {t("action.title")}
      </h3>

      {action.type === "safety_alert" && (
        <div role="alert" className="flex flex-col gap-1 rounded-md border-2 border-danger p-3">
          <Badge tone="danger">{t("action.safetyTitle")}</Badge>
          <Row>{t("action.safetyBody")}</Row>
        </div>
      )}

      {action.type === "incident_merge" && (
        <div className="flex flex-col gap-1">
          <Badge tone="info">{t("action.incidentTitle")}</Badge>
          <Row>{t("action.incidentBody")}</Row>
        </div>
      )}

      {action.type === "booking" && action.booking && (
        <div className="flex flex-col gap-1">
          <h4 className="text-sm font-semibold text-fg-1">{t("action.bookingTitle")}</h4>
          <Row>{t("action.bookingWith", { name: action.booking.advisor_name })}</Row>
          <Row>
            <span dir="ltr">
              {t("action.bookingTime", {
                start: fmt(action.booking.starts_at),
                end: timeOnly.format(new Date(action.booking.ends_at)),
              })}
            </span>
          </Row>
          {action.booking.room && <Row>{t("action.bookingRoom", { room: action.booking.room })}</Row>}
        </div>
      )}

      {action.type === "faq_answer" && action.faq && (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <h4 className="text-sm font-semibold text-fg-1">{t("action.faqTitle")}</h4>
            {action.faq.is_demo && <Badge tone="warn">{t("action.faqDemo")}</Badge>}
          </div>
          <p dir={textDir(action.faq.question)} className="text-sm font-medium text-fg-1">
            {action.faq.question}
          </p>
          <p dir={textDir(action.faq.answer)} className="text-sm text-fg-1">
            {action.faq.answer}
          </p>
          {action.faq.is_demo && <Row>{t("action.faqDemoNote")}</Row>}
          {safeHref(action.faq.source_url) && (
            <Row>
              {t("action.faqSource")}:{" "}
              <a
                href={safeHref(action.faq.source_url)!}
                target="_blank"
                rel="noreferrer noopener"
                dir="ltr"
                className="break-all font-medium text-accent underline underline-offset-2"
              >
                {action.faq.source_url}
              </a>
            </Row>
          )}
        </div>
      )}

      {showTicket && (
        <div className="flex flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={action.provisional ? "warn" : "ok"}>
              {action.provisional ? t("action.ticketProvisional") : t("action.ticketOpened")}
            </Badge>
            {action.external.map((r) => (
              <ExternalLink key={`${r.sink}-${r.external_id}`} r={r} label={r.sink === "linear" ? t("action.linearLink", { id: r.external_id }) : r.external_id} />
            ))}
          </div>
          {action.sla_due_at && <Row>{t("action.sla", { date: fmt(action.sla_due_at) })}</Row>}
        </div>
      )}

      {deferred && <Row>{t("action.deferred")}</Row>}
    </section>
  );
}
