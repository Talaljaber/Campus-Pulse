"use client";

import { useMemo, useState } from "react";
import { useLabMetrics, useRedTeam } from "@/hooks/useLab";
import { useLang, useT, type DictKey } from "@/i18n";
import type { RedTeamRunRequest } from "@/lib/ai/types";
import { mergeScorecards, noOfflineReport, percent } from "@/lib/lab/metrics";
import { formatDateTime } from "@/lib/time";
import { AppShell } from "../shell/AppShell";
import { PageHeader } from "../shell/PageHeader";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { EmptyState } from "../ui/EmptyState";
import { Loadable } from "../ui/Loadable";
import { TabPanel, Tabs } from "../ui/Tabs";
import { useToast } from "../ui/Toast";
import { AblationTable } from "./AblationTable";
import { BenchmarkTable } from "./BenchmarkTable";
import { CalibrationTable } from "./CalibrationTable";
import { ConfusionMatrix } from "./ConfusionMatrix";
import { CoverageChart } from "./CoverageChart";
import { FairnessChart } from "./FairnessChart";
import { MemoryStats } from "./MemoryStats";
import { RedTeamRunner } from "./RedTeamRunner";
import { RouterStats } from "./RouterStats";
import { ScorecardHistory } from "./ScorecardHistory";

const TAB_IDS = ["benchmark", "calibration", "live", "redteam"] as const;
type TabId = (typeof TAB_IDS)[number];
const ID_BASE = "lab";

/** Props for {@link LabScreen}. */
export interface LabScreenProps {
  /** The signed-in admin's alias, for the header greeting. */
  alias?: string | null;
}

/**
 * The model lab `/lab` (admin): the benchmark, calibration and fairness numbers from the evaluation
 * report, the live router and memory, and the red team. It only wires `GET /v1/metrics` and
 * `POST /v1/redteam/run` to presentational sections. Without an evaluation report the offline tabs
 * say so plainly and the live system and the red team keep working.
 */
export function LabScreen({ alias = null }: LabScreenProps) {
  const t = useT();
  const { lang } = useLang();
  const toast = useToast();
  const metrics = useLabMetrics();
  const redTeam = useRedTeam();
  const [tab, setTab] = useState<TabId>("benchmark");

  const data = metrics.data;
  const history = useMemo(() => mergeScorecards(redTeam.runs, data?.redteam ?? []), [redTeam.runs, data]);

  const onRun = async (req: RedTeamRunRequest) => {
    const out = await redTeam.run(req);
    if (out.ok) {
      toast.show(t("lab.redteam.done", { pct: percent(out.scorecard.overall) }), "ok");
      metrics.refresh();
    } else {
      toast.show(t(`lab.error.${out.kind}` as DictKey), "danger");
    }
  };

  const items = TAB_IDS.map((id) => ({ id, label: t(`lab.tabs.${id}` as DictKey) }));
  const offlineEmpty = data !== null && noOfflineReport(data);
  const empty = <EmptyState title={t("lab.empty.title")} hint={t("lab.empty.hint")} />;

  return (
    <AppShell role="admin" current="lab" alias={alias}>
      <PageHeader title={t("lab.title")} subtitle={t("lab.subtitle")} />

      <div className="flex flex-wrap items-center gap-2">
        {data && (
          <>
            <Badge tone="info" icon={null}>
              {data.artifact.version === "none" || data.artifact.version === ""
                ? t("lab.status.noArtifact")
                : t("lab.status.artifact", { version: data.artifact.version, sha: data.artifact.sha.slice(0, 8) })}
            </Badge>
            <Badge tone="neutral" icon={null}>
              {data.generated_at ? t("lab.status.generated", { when: formatDateTime(data.generated_at, lang) }) : t("lab.status.noReport")}
            </Badge>
            {data.ask_rate !== null && (
              <Badge tone="neutral" icon={null}>
                {t("lab.status.askRate", { pct: percent(data.ask_rate) })}
                {data.ask_rate_is_proxy ? `, ${t("lab.status.proxy")}` : ""}
              </Badge>
            )}
          </>
        )}
        <Button variant="secondary" size="sm" onClick={metrics.reload}>
          {t("lab.refresh")}
        </Button>
      </div>

      <Tabs items={items} value={tab} onChange={(id) => setTab(id as TabId)} label={t("lab.tabs.label")} idBase={ID_BASE} />

      <TabPanel idBase={ID_BASE} id="benchmark" value={tab}>
        <Loadable state={metrics.load} onRetry={metrics.reload} lines={8}>
          {data && (offlineEmpty ? empty : (
            <div className="flex flex-col gap-6">
              <section className="flex flex-col gap-3" aria-label={t("lab.benchmark.title")}>
                <h3 className="text-lg font-semibold">{t("lab.benchmark.title")}</h3>
                <BenchmarkTable rows={data.benchmark} />
              </section>
              <AblationTable rows={data.ablations} />
              <ConfusionMatrix confusions={data.confusions} />
            </div>
          ))}
        </Loadable>
      </TabPanel>

      <TabPanel idBase={ID_BASE} id="calibration" value={tab}>
        <Loadable state={metrics.load} onRetry={metrics.reload} lines={8}>
          {data && (offlineEmpty ? empty : (
            <div className="flex flex-col gap-6">
              <CoverageChart rows={data.coverage} />
              <CalibrationTable curves={data.calibration} />
              <FairnessChart rows={data.fairness} />
            </div>
          ))}
        </Loadable>
      </TabPanel>

      <TabPanel idBase={ID_BASE} id="live" value={tab}>
        <Loadable state={metrics.load} onRetry={metrics.reload} lines={6}>
          {data && (
            <div className="flex flex-col gap-6">
              <RouterStats router={data.router} />
              <MemoryStats memory={data.memory} />
            </div>
          )}
        </Loadable>
      </TabPanel>

      <TabPanel idBase={ID_BASE} id="redteam" value={tab}>
        <div className="flex flex-col gap-6">
          <RedTeamRunner running={redTeam.running} onRun={(req) => void onRun(req)} />
          <ScorecardHistory runs={history} />
        </div>
      </TabPanel>
    </AppShell>
  );
}
