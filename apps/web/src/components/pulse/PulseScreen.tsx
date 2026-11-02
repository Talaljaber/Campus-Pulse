"use client";

import { useMemo, useState } from "react";
import { useMapBuildings } from "@/hooks/useMapBuildings";
import { usePulse } from "@/hooks/usePulse";
import { useLang, useT, type DictKey } from "@/i18n";
import { dotsOf, openIncidents, ringsOf } from "@/lib/pulse/view";
import { AppShell } from "../shell/AppShell";
import { PageHeader } from "../shell/PageHeader";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { Loadable } from "../ui/Loadable";
import { useToast } from "../ui/Toast";
import { EventFeed } from "./EventFeed";
import { IncidentList } from "./IncidentList";
import { CampusMap, IncidentRing, MapLegend, RequestDot } from "./map";

/** Props for {@link PulseScreen}. */
export interface PulseScreenProps {
  /** Decides which links the header offers (an admin also gets the model lab). */
  role: "staff" | "admin";
  /** The signed-in user's alias, for the header greeting. */
  alias?: string | null;
}

/**
 * The Pulse page `/pulse`: the campus map with a dot per request and a pulsing ring per open
 * incident, the incident list (with resolve) and the live feed. Choosing a building narrows the
 * incident list to it. It only wires `usePulse` to presentational components; staff see the
 * rows of their office and an admin sees all, by row-level security.
 */
export function PulseScreen({ role, alias = null }: PulseScreenProps) {
  const t = useT();
  const { lang } = useLang();
  const toast = useToast();
  const buildings = useMapBuildings();
  const pulse = usePulse();
  const [selected, setSelected] = useState<string | null>(null);

  const dots = useMemo(() => dotsOf(pulse.state, buildings), [pulse.state, buildings]);
  const rings = useMemo(() => ringsOf(pulse.state, buildings), [pulse.state, buildings]);
  const incidents = useMemo(() => openIncidents(pulse.state, selected), [pulse.state, selected]);
  const selectedBuilding = buildings.find((b) => b.id === selected);

  const onResolve = async (id: string, note?: string) => {
    const out = await pulse.resolve(id, note);
    if (!out.ok) toast.show(t(`pulse.error.${out.kind}` as DictKey), "danger");
    else toast.show(t("pulse.toast.resolved", { count: out.notified }), "ok");
  };

  return (
    <AppShell role={role} current="incidents" alias={alias} width="wide">
      <PageHeader title={t("pulse.title")} subtitle={t("pulse.subtitle")} badges={<Badge tone="ok">{t("pulse.live")}</Badge>} />

      <Loadable state={pulse.load} onRetry={pulse.reload} lines={6}>
        <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <section aria-label={t("pulse.mapSection")} className="flex flex-col gap-3">
            <CampusMap buildings={buildings} selected={selected ?? undefined} onBuildingClick={(id) => setSelected((cur) => (cur === id ? null : id))}>
              {dots.map((d) => (
                <RequestDot key={d.id} x={d.x} y={d.y} category={d.category} priority={d.priority} simulated={d.simulated} />
              ))}
              {rings.map((r) => (
                <IncidentRing key={r.id} x={r.x} y={r.y} priority={r.priority} reportCount={r.reportCount} />
              ))}
            </CampusMap>
            <MapLegend />
          </section>

          <div className="flex flex-col gap-4">
            <Card title={t("pulse.incidents")}>
              {selectedBuilding && (
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  <Badge tone="info" icon={null}>
                    {t("pulse.selectedBuilding", { code: selectedBuilding.code, name: lang === "ar" ? selectedBuilding.name_ar : selectedBuilding.name_en })}
                  </Badge>
                  <Button variant="ghost" size="sm" onClick={() => setSelected(null)}>
                    {t("pulse.clearBuilding")}
                  </Button>
                </div>
              )}
              <IncidentList incidents={incidents} buildings={buildings} onResolve={onResolve} />
            </Card>
            <Card title={t("pulse.feed")}>
              <div className="max-h-[28rem] overflow-y-auto">
                <EventFeed events={pulse.state.feed} />
              </div>
            </Card>
          </div>
        </div>
      </Loadable>
    </AppShell>
  );
}
