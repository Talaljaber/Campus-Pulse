"use client";

import { useState, type ReactNode } from "react";
import {
  Badge,
  Button,
  Card,
  ChipGroup,
  Dialog,
  EmptyState,
  LanguageSwitch,
  Skeleton,
  Table,
  TabPanel,
  Tabs,
  ThemeSwitch,
  ToastProvider,
  useToast,
  CATEGORY_TONE,
  PRIORITY_TONE,
  type Tone,
} from "@/components/ui";
import { MapStories } from "./MapStories";
import { TriageStories } from "./TriageStories";
import { CATEGORY_VALUES, LangScope, PRIORITY_VALUES, labelOf, useLang, useT, type Lang } from "@/i18n";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-xl font-semibold text-fg-1">{title}</h2>
      {children}
    </section>
  );
}

interface OfficeRow {
  id: string;
  office: string;
  open: number;
  sla: string;
}

function Showcase() {
  const t = useT();
  const { lang } = useLang();
  const toast = useToast();
  const [chip, setChip] = useState<string | null>("Registration");
  const [tab, setTab] = useState("overview");
  const [dialog, setDialog] = useState(false);

  const rows: OfficeRow[] = [
    { id: "it", office: "IT", open: 4, sla: "2h" },
    { id: "reg", office: labelOf("category", "Registration", lang), open: 11, sla: "8h" },
  ];

  return (
    <div className="flex flex-col gap-6">
      <Section title={t("devui.buttons")}>
        <div className="flex flex-wrap gap-2">
          <Button>{t("devui.primary")}</Button>
          <Button variant="secondary">{t("devui.secondary")}</Button>
          <Button variant="ghost">{t("devui.ghost")}</Button>
          <Button variant="danger">{t("devui.danger")}</Button>
          <Button size="sm">sm</Button>
          <Button loading>{t("devui.loadingBtn")}</Button>
          <Button disabled>{t("devui.disabled")}</Button>
        </div>
      </Section>

      <Section title={t("devui.chips")}>
        <ChipGroup
          label={t("devui.chipPick")}
          value={chip}
          onChange={setChip}
          items={CATEGORY_VALUES.map((c) => ({ id: c, label: labelOf("category", c, lang), tone: CATEGORY_TONE[c] as Tone }))}
        />
      </Section>

      <Section title={t("devui.badges")}>
        <div className="flex flex-wrap gap-2">
          {CATEGORY_VALUES.map((c) => (
            <Badge key={c} tone={CATEGORY_TONE[c]}>
              {labelOf("category", c, lang)}
            </Badge>
          ))}
        </div>
        <div className="flex flex-wrap gap-2">
          {PRIORITY_VALUES.map((p) => (
            <Badge key={p} tone={PRIORITY_TONE[p]}>
              {labelOf("priority", p, lang)}
            </Badge>
          ))}
          <Badge tone="ok">ok</Badge>
          <Badge tone="warn">warn</Badge>
          <Badge tone="danger">danger</Badge>
          <Badge tone="info">info</Badge>
          <Badge>neutral</Badge>
        </div>
      </Section>

      <Section title={t("devui.cards")}>
        <Card title={t("devui.sampleCardTitle")} actions={<Badge tone="pri-high">{labelOf("priority", "high", lang)}</Badge>}>
          <p className="text-fg-2">{t("devui.sampleCardBody")}</p>
        </Card>
      </Section>

      <Section title={t("devui.tabs")}>
        <Tabs
          idBase={`ks-${lang}`}
          label={t("devui.tabs")}
          value={tab}
          onChange={setTab}
          items={[
            { id: "overview", label: t("devui.tabOverview") },
            { id: "tickets", label: t("devui.tabTickets") },
            { id: "incidents", label: t("devui.tabIncidents") },
          ]}
        />
        <TabPanel idBase={`ks-${lang}`} id="overview" value={tab}>
          <p className="py-3 text-fg-2">{t("devui.tabOverview")}</p>
        </TabPanel>
        <TabPanel idBase={`ks-${lang}`} id="tickets" value={tab}>
          <p className="py-3 text-fg-2">{t("devui.ticketsTab", { office: "IT" })}</p>
        </TabPanel>
        <TabPanel idBase={`ks-${lang}`} id="incidents" value={tab}>
          <p className="py-3 text-fg-2">{t("devui.tabIncidents")}</p>
        </TabPanel>
      </Section>

      <Section title={t("devui.table")}>
        <Table<OfficeRow>
          caption={t("devui.table")}
          rowKey={(r) => r.id}
          rows={rows}
          columns={[
            { key: "office", header: t("devui.colOffice") },
            { key: "open", header: t("devui.colOpen"), align: "end" },
            { key: "sla", header: t("devui.colSla"), align: "end" },
          ]}
        />
        <Table<OfficeRow> caption={t("devui.emptyState")} rowKey={(r) => r.id} rows={[]} columns={[{ key: "office", header: t("devui.colOffice") }]} />
      </Section>

      <Section title={t("devui.toast")}>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => toast.show(t("devui.toastMessage"), "ok")}>
            {t("devui.showToast")}
          </Button>
        </div>
      </Section>

      <Section title={t("devui.dialog")}>
        <div>
          <Button variant="secondary" onClick={() => setDialog(true)}>
            {t("devui.openDialog")}
          </Button>
        </div>
        <Dialog open={dialog} onClose={() => setDialog(false)} title={t("devui.dialogTitle")}>
          <p>{t("devui.dialogBody")}</p>
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setDialog(false)}>
              {t("common.cancel")}
            </Button>
            <Button onClick={() => setDialog(false)}>{t("common.confirm")}</Button>
          </div>
        </Dialog>
      </Section>

      <Section title={t("devui.triageTitle")}>
        <TriageStories />
      </Section>

      <Section title={t("devui.mapTitle")}>
        <MapStories />
      </Section>

      <Section title={t("devui.skeleton")}>
        <Skeleton lines={3} />
      </Section>

      <Section title={t("devui.emptyState")}>
        <EmptyState title={t("ui.emptyState.defaultTitle")} hint={t("devui.emptyHint")} action={<Button size="sm">{t("devui.emptyAction")}</Button>} />
      </Section>
    </div>
  );
}

function Column({ lang }: { lang: Lang }) {
  return (
    <LangScope lang={lang} className="min-w-0 rounded-lg border border-line bg-surface-0 p-4">
      <ToastProvider>
        <Showcase />
      </ToastProvider>
    </LangScope>
  );
}

/** Every `ui/*` primitive in English and Arabic (RTL) side by side. Dev only. */
export function KitchenSink() {
  const t = useT();
  return (
    <main className="mx-auto flex max-w-7xl flex-col gap-6 p-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-fg-1">{t("devui.title")}</h1>
          <p className="text-fg-2">{t("devui.intro")}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <LanguageSwitch />
          <ThemeSwitch />
        </div>
      </header>
      <div className="grid gap-4 lg:grid-cols-2">
        <Column lang="en" />
        <Column lang="ar" />
      </div>
    </main>
  );
}
