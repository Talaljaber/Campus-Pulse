"use client";

import { useT } from "@/i18n";
import { textDir } from "../explain/text";
import { Icon } from "../ui/Icon";

/** Props for {@link DistressCard}. */
export interface DistressCardProps {
  /** The service's supportive message: it names the counselling service (placeholder) and 911. Shown as written. */
  message: string;
}

/**
 * The reply to a distress signal. It shows the supportive message and nothing else: no
 * category, no priority, no ticket. The wording comes from the service on purpose, so it
 * is not reworded here; it is announced politely and is not styled as an error.
 */
export function DistressCard({ message }: DistressCardProps) {
  const t = useT();
  return (
    <section role="status" className="flex max-w-prose flex-col gap-2 rounded-lg border-2 border-info bg-surface-1 p-4">
      <h2 className="flex items-center gap-2 text-lg font-semibold text-fg-1">
        <Icon name="info" size={18} className="text-info" />
        {t("chat.distressTitle")}
      </h2>
      <p dir={textDir(message)} className="text-fg-1">
        {message}
      </p>
    </section>
  );
}
