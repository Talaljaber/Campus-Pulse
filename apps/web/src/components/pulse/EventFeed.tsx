"use client";

import { labelOf, useLang, useT } from "@/i18n";
import type { FeedEvent } from "@/lib/pulse/state";
import { useNow } from "../explain/useNow";
import { Badge } from "../ui/Badge";
import { EmptyState } from "../ui/EmptyState";
import { useDuration } from "../ui/useDuration";

/** Props for {@link EventFeed}. */
export interface EventFeedProps {
  /** Newest first, as the Pulse state keeps them. */
  events: readonly FeedEvent[];
  /** Epoch ms to pin the clock (tests, stories). */
  now?: number;
}

/**
 * The live feed: new requests, incidents opening, growing and closing, and broadcasts. Every line
 * is a sentence in the page language built from structured fields; the free text (an incident
 * title) is shown as the service wrote it. Demo traffic carries a visible SIMULATED badge. The list
 * is a polite `log` region, so screen readers hear new lines without losing their place.
 */
export function EventFeed({ events, now }: EventFeedProps) {
  const t = useT();
  const { lang } = useLang();
  const span = useDuration();
  const clock = useNow(now);

  if (events.length === 0) return <EmptyState title={t("pulse.feedEmpty")} hint={t("pulse.feedEmptyHint")} />;

  const sentence = (e: FeedEvent): string => {
    const title = e.title ?? "";
    switch (e.kind) {
      case "request":
        return t("pulse.event.request", {
          category: e.category ? labelOf("category", e.category, lang) : "",
          priority: e.priority ? labelOf("priority", e.priority, lang) : "",
          where: e.buildingId ? t("pulse.event.where", { code: e.buildingId }) : "",
        });
      case "incident_new":
        return t("pulse.event.incident_new", { title });
      case "incident_bump":
        return t("pulse.event.incident_bump", { title, count: e.count ?? 0 });
      case "resolved":
        return t("pulse.event.resolved", { title });
      case "broadcast":
        return t("pulse.event.broadcast", { title });
    }
  };

  return (
    <ol role="log" aria-label={t("pulse.feed")} className="flex flex-col gap-2">
      {events.map((e) => (
        <li key={e.id} data-kind={e.kind} className="flex flex-col gap-1 rounded-md border border-line bg-surface-1 px-3 py-2 text-sm">
          <p dir="auto" className="text-fg-1">
            {sentence(e)}
          </p>
          <div className="flex flex-wrap items-center gap-2">
            {e.simulated && (
              <Badge tone="info" icon={null}>
                {t("pulse.simulated")}
              </Badge>
            )}
            {clock !== null && <span className="text-xs text-fg-3">{t("pulse.event.ago", { span: span(clock - new Date(e.at).getTime()) })}</span>}
          </div>
        </li>
      ))}
    </ol>
  );
}
