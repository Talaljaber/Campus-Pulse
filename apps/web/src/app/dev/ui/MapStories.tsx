"use client";

import { useState } from "react";
import { CampusMap, FIXTURE_BUILDINGS, IncidentRing, MapLegend, RequestDot } from "@/components/pulse/map";
import { useT } from "@/i18n";
import { FIXTURE_DOTS, FIXTURE_RINGS } from "@/lib/fixtures/map";

/** Story for the P5.5 map primitives: 20 fixture dots, one incident ring, selectable buildings. */
export function MapStories() {
  const t = useT();
  const [selected, setSelected] = useState<string | undefined>();
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-fg-2">{t("devui.mapHint")}</p>
      <CampusMap buildings={FIXTURE_BUILDINGS} selected={selected} onBuildingClick={setSelected}>
        {FIXTURE_DOTS.map((d) => (
          <RequestDot key={d.id} x={d.x} y={d.y} category={d.category} priority={d.priority} simulated={d.simulated} />
        ))}
        {FIXTURE_RINGS.map((r) => (
          <IncidentRing key={r.id} x={r.x} y={r.y} priority={r.priority} reportCount={r.reportCount} />
        ))}
      </CampusMap>
      <p role="status" className="text-sm text-fg-1">
        {selected ? t("devui.mapSelected", { code: selected }) : t("devui.mapNone")}
      </p>
      <MapLegend />
    </div>
  );
}
