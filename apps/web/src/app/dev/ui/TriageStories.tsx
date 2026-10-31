"use client";

import { useState } from "react";
import { ActionSummary, FlagBadges, ResultCard, UnderstandingView, type Audience } from "@/components/chat";
import { EvidenceText } from "@/components/explain";
import { CATEGORY_TONE, ChipGroup, PRIORITY_TONE, ProbBar, SetBadge } from "@/components/ui";
import { labelOf, useLang, useT, type DictKey } from "@/i18n";
import type { CounterfactualView } from "@/lib/ai/types";
import { COUNTERFACTUAL_FIXTURE, TRIAGE_FIXTURES, type TriageFixtureName } from "@/lib/fixtures/api";

const NAMES = Object.keys(TRIAGE_FIXTURES) as TriageFixtureName[];
const AUDIENCES: Audience[] = ["student", "staff", "admin"];

/**
 * Stories for the P5.4 components, built from the real API fixtures (EN, AR, Arabizi,
 * all five statuses). The counterfactual click is faked locally with the fixture
 * answer: the components never fetch.
 */
export function TriageStories() {
  const t = useT();
  const { lang } = useLang();
  const [name, setName] = useState<TriageFixtureName>("enMemory");
  const [audience, setAudience] = useState<Audience>("student");
  const [cf, setCf] = useState<CounterfactualView | null>(null);
  const { text, response } = TRIAGE_FIXTURES[name];

  return (
    <div className="flex flex-col gap-4">
      <ChipGroup
        label={t("devui.fixturePick")}
        value={name}
        onChange={(id) => {
          setName(id as TriageFixtureName);
          setCf(null);
        }}
        items={NAMES.map((n) => ({ id: n, label: t(`devui.fx.${n}` satisfies DictKey) }))}
      />
      <ChipGroup
        label={t("devui.audiencePick")}
        value={audience}
        onChange={(id) => setAudience(id as Audience)}
        items={AUDIENCES.map((a) => ({ id: a, label: t(`devui.audience.${a}`) }))}
      />

      <ResultCard
        result={response}
        audience={audience}
        text={text}
        counterfactual={cf}
        onCounterfactual={(token) => setCf({ ...COUNTERFACTUAL_FIXTURE, request_id: response.request_id, drop: token })}
      />

      <h3 className="text-lg font-semibold text-fg-1">{t("devui.parts")}</h3>
      <div className="flex flex-col gap-4">
        {response.category && (
          <>
            <ProbBar
              label={labelOf("category", response.category.label, lang)}
              prob={response.category.prob}
              tone={CATEGORY_TONE[response.category.label]}
            />
            <SetBadge set={response.category.set} kind="category" chosen={response.category.label} />
          </>
        )}
        {response.priority && (
          <>
            <ProbBar
              label={labelOf("priority", response.priority.label, lang)}
              prob={response.priority.prob}
              tone={PRIORITY_TONE[response.priority.label]}
            />
            <SetBadge set={response.priority.set} kind="priority" chosen={response.priority.label} />
          </>
        )}
        {response.explanation && (
          <EvidenceText text={text} tokens={response.explanation.top_tokens} evidence={response.priority?.evidence} />
        )}
        <FlagBadges flags={response.flags} audience={audience} />
        <UnderstandingView understanding={response.understanding} showTicketDraft={audience !== "student"} />
        <ActionSummary action={response.action} status={response.status} />
      </div>
    </div>
  );
}
