"use client";

import { useState } from "react";
import { labelOf, useLang, useT } from "@/i18n";
import type { IncidentView } from "@/lib/incidents";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { EmptyState } from "../ui/EmptyState";
import { TextArea } from "../ui/TextField";
import { CATEGORY_TONE, PRIORITY_TONE } from "../ui/tone";
import { useDuration } from "../ui/useDuration";
import { useNow } from "../explain/useNow";
import { buildingName, tidyLabel, type Building } from "./map/campus";

/** Props for {@link IncidentList}. */
export interface IncidentListProps {
  incidents: readonly IncidentView[];
  /** Buildings, to print a building's name next to its code. Without them only the code is shown. */
  buildings?: readonly Building[];
  /** Show a Resolve button (staff and admin). It opens a confirmation first; `note` is the optional message to reporters. The dialog stays open until the returned promise settles. */
  onResolve?: (id: string, note?: string) => void | Promise<void>;
  /** Epoch ms to pin "opened N ago" (tests, stories). Defaults to the real time. */
  now?: number;
}

/**
 * Open incidents, newest first. Each shows its title, building, category, priority, report
 * count and age. Resolving asks for confirmation, because it closes the member tickets and
 * messages every reporter, and offers an optional note for them.
 */
export function IncidentList({ incidents, buildings = [], onResolve, now }: IncidentListProps) {
  const t = useT();
  const { lang } = useLang();
  const span = useDuration();
  const clock = useNow(now);
  const [target, setTarget] = useState<IncidentView | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const where = (id: string) => {
    const b = buildings.find((x) => x.id === id || x.code === id);
    return b ? tidyLabel(t("pulse.incident.inBuilding", { code: b.code, name: buildingName(b, lang) })) : id;
  };

  const close = () => {
    setTarget(null);
    setNote("");
  };

  if (incidents.length === 0) return <EmptyState title={t("pulse.incident.empty")} hint={t("pulse.incident.emptyHint")} />;

  return (
    <>
      <ul aria-label={t("pulse.incidents")} className="flex flex-col gap-2">
        {incidents.map((i) => (
          <li key={i.id} data-incident={i.id} className="flex flex-col gap-2 rounded-lg border border-line bg-surface-1 p-3">
            <p dir="auto" className="text-base font-semibold text-fg-1">
              {i.title}
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={CATEGORY_TONE[i.category] ?? "neutral"}>{labelOf("category", i.category, lang)}</Badge>
              <Badge tone={PRIORITY_TONE[i.priority] ?? "neutral"}>{labelOf("priority", i.priority, lang)}</Badge>
              <span className="text-sm text-fg-2">{t("pulse.incident.reports", { count: i.reportCount })}</span>
              {clock !== null && (
                <span className="text-sm text-fg-3">{t("pulse.incident.opened", { span: span(clock - new Date(i.openedAt).getTime()) })}</span>
              )}
            </div>
            <p className="text-sm text-fg-2">{where(i.buildingId)}</p>
            {onResolve && (
              <div>
                <Button variant="secondary" size="sm" onClick={() => setTarget(i)}>
                  {t("pulse.incident.resolve")}
                </Button>
              </div>
            )}
          </li>
        ))}
      </ul>

      <Dialog open={target !== null} onClose={close} title={t("pulse.incident.resolveTitle")}>
        {target && (
          <div className="flex flex-col gap-3">
            <p dir="auto" className="font-medium text-fg-1">
              {target.title}
            </p>
            <p>{t("pulse.incident.resolveBody")}</p>
            <TextArea label={t("pulse.incident.noteLabel")} value={note} onChange={(e) => setNote(e.target.value)} rows={2} />
            <div className="flex flex-wrap justify-end gap-2">
              <Button variant="ghost" onClick={close}>
                {t("common.cancel")}
              </Button>
              <Button
                loading={busy}
                onClick={async () => {
                  setBusy(true);
                  try {
                    await onResolve?.(target.id, note.trim() || undefined);
                  } finally {
                    setBusy(false);
                    close();
                  }
                }}
              >
                {t("pulse.incident.confirm")}
              </Button>
            </div>
          </div>
        )}
      </Dialog>
    </>
  );
}
