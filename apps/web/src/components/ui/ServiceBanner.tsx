"use client";

import { useT } from "@/i18n";
import { cn } from "./cn";
import { Icon } from "./Icon";

/** Props for {@link ServiceBanner}. */
export interface ServiceBannerProps {
  /** `ok` renders nothing visible; `waking` is a Render cold start; `down` is a real outage. */
  state: "ok" | "waking" | "down";
  className?: string;
}

/**
 * Tells the user the AI service is starting or unavailable. The wrapper is a polite live
 * region that is always in the DOM, so a screen reader announces the change when it appears.
 * Presentational: the polling lives in `useServiceHealth`.
 */
export function ServiceBanner({ state, className }: ServiceBannerProps) {
  const t = useT();
  return (
    <div role="status" aria-live="polite" aria-label={t("service.label")} className={className} data-state={state}>
      {state !== "ok" && (
        <p
          className={cn(
            "flex items-center gap-2 border-b-2 px-4 py-2 text-sm text-fg-1",
            state === "waking" ? "border-warn bg-surface-1" : "border-danger bg-surface-1",
          )}
        >
          <Icon name={state === "waking" ? "spinner" : "alert"} size={16} className={state === "waking" ? "text-warn" : "text-danger"} />
          {t(state === "waking" ? "service.waking" : "service.down")}
        </p>
      )}
    </div>
  );
}
