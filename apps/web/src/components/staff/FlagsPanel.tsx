"use client";

import { useT } from "@/i18n";
import { type FlagEvent } from "@/lib/staff/flags";
import { textDir } from "../explain/text";
import { useNow } from "../explain/useNow";
import { FlagBadges, isFlagVisible, type Audience } from "../chat/FlagBadges";
import { Card } from "../ui/Card";
import { EmptyState } from "../ui/EmptyState";
import { useDuration } from "../ui/useDuration";

/** Props for {@link FlagsPanel}. */
export interface FlagsPanelProps {
  events: readonly FlagEvent[];
  /** Decides which flags are shown: gaming suspicion is admin only. An event with no visible flag is hidden. */
  audience: Exclude<Audience, "student">;
  /** Epoch ms to pin the clock (tests, stories). */
  now?: number;
}

/**
 * Requests whose decision carried an injection, unsupported-urgency or gaming flag. Informational
 * only: a flag never changes a label. The request text is shown as written, in its own direction.
 */
export function FlagsPanel({ events, audience, now }: FlagsPanelProps) {
  const t = useT();
  const span = useDuration();
  const clock = useNow(now);
  const shown = events.filter((e) => e.flags.some((f) => isFlagVisible(f, audience)));
  return (
    <Card title={t("staff.flags.title")}>
      <p className="mb-3 text-sm text-fg-2">{t("staff.flags.hint")}</p>
      {shown.length === 0 ? (
        <EmptyState title={t("staff.flags.empty")} />
      ) : (
        <ul className="flex flex-col gap-2">
          {shown.map((e) => (
            <li key={e.id} className="flex flex-col gap-2 rounded-md border border-line bg-surface-0 p-3">
              {e.text && (
                <p dir={textDir(e.text)} className="text-sm text-fg-1">
                  {e.text}
                </p>
              )}
              <div className="flex flex-wrap items-center gap-2">
                <FlagBadges flags={e.flags} audience={audience} />
                {clock !== null && <span className="text-xs text-fg-3">{span(clock - new Date(e.at).getTime())}</span>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
