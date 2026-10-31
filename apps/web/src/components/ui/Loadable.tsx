"use client";

import type { ReactNode } from "react";
import { useT } from "@/i18n";
import { Button } from "./Button";
import { Skeleton } from "./Skeleton";

/** Props for {@link Loadable}. */
export interface LoadableProps {
  /** `loading` shows a skeleton, `error` a message with a retry button, `ready` the children. */
  state: "loading" | "ready" | "error";
  onRetry?: () => void;
  /** Number of skeleton lines while loading. Default 4. */
  lines?: number;
  children: ReactNode;
}

/** The three states every list on the staff and pulse pages share: loading, failed (with retry), ready. */
export function Loadable({ state, onRetry, lines = 4, children }: LoadableProps) {
  const t = useT();
  if (state === "loading") return <Skeleton lines={lines} />;
  if (state === "error") {
    return (
      <div role="alert" className="flex flex-col items-start gap-3 rounded-lg border border-line-strong bg-surface-1 p-4">
        <p className="text-fg-1">{t("common.loadFailed")}</p>
        {onRetry && (
          <Button variant="secondary" size="sm" onClick={onRetry}>
            {t("common.retry")}
          </Button>
        )}
      </div>
    );
  }
  return <>{children}</>;
}
