"use client";

import { labelOf, useLang, useT } from "@/i18n";
import { Badge } from "../ui/Badge";
import { PRIORITY_TONE } from "../ui/tone";

/** Priority as a badge with an icon; `high` reads "Urgent" so it is never only a colour. */
export function PriorityBadge({ priority }: { priority: string }) {
  const t = useT();
  const { lang } = useLang();
  return <Badge tone={PRIORITY_TONE[priority] ?? "neutral"}>{priority === "high" ? t("queue.urgent") : labelOf("priority", priority, lang)}</Badge>;
}
