"use client";

import { useT } from "@/i18n";
import type { IncidentView } from "@/lib/incidents";
import { IncidentList } from "../pulse/IncidentList";
import type { Building } from "../pulse/map/campus";
import { Card } from "../ui/Card";

/** Props for {@link IncidentsPanel}. */
export interface IncidentsPanelProps {
  incidents: readonly IncidentView[];
  buildings?: readonly Building[];
  /** Resolve an incident (optional note to the reporters). The panel's dialog waits for the promise. */
  onResolve: (id: string, note?: string) => void | Promise<void>;
}

/** The open incidents of the staff member's office, with the resolve action. A titled card around {@link IncidentList}. */
export function IncidentsPanel({ incidents, buildings, onResolve }: IncidentsPanelProps) {
  const t = useT();
  return (
    <Card title={t("staff.incidents.title")}>
      <IncidentList incidents={incidents} buildings={buildings} onResolve={onResolve} />
    </Card>
  );
}
