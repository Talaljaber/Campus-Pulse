"use client";

import Link from "next/link";
import { useId, useState, type ReactNode } from "react";
import { labelOf, useLang, useT, type DictKey } from "@/i18n";
import type { CounterfactualView, TriageResponse } from "@/lib/ai/types";
import { fetchCounterfactual } from "@/lib/chat/service";
import type { ProposalOut } from "@/lib/chat/agentTypes";
import { CounterfactualHint } from "../explain/CounterfactualHint";
import { textDir } from "../explain/text";
import { useOfficeLabel } from "../staff/office";
import { Button } from "../ui/Button";
import { ChipGroup } from "../ui/Chip";

const SOURCES = new Set(["train", "augmented", "memory"]);

/** The "Why this?" button and its panel. Hidden by default: probabilities and sets live only in here. */
function Why({ children }: { children: ReactNode }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const panel = useId();
  return (
    <div className="flex flex-col gap-2">
      <div>
        <Button size="sm" variant="ghost" aria-expanded={open} aria-controls={panel} onClick={() => setOpen((v) => !v)}>
          {t("chat.agent.why")}
        </Button>
      </div>
      <div id={panel} hidden={!open} className="flex flex-col gap-2 rounded-md bg-surface-2 p-3 text-sm text-fg-2">
        {open && children}
      </div>
    </div>
  );
}

/** What the model based the suggestion on: category and priority with their numbers, a past correction, similar requests. */
function WhyDetails({ proposal }: { proposal: ProposalOut }) {
  const t = useT();
  const { lang } = useLang();
  const { why, hint } = proposal;
  const cat = (v: string) => labelOf("category", v, lang);
  const pri = (v: string) => labelOf("priority", v, lang);
  return (
    <>
      <p>
        {t("chat.agent.whyCategory", {
          label: cat(why.category.label),
          pct: Math.round(why.category.prob * 100),
          set: why.category.set.map(cat).join(", "),
        })}
      </p>
      <p>
        {t("chat.agent.whyPriority", {
          label: pri(why.priority.label),
          pct: Math.round(why.priority.prob * 100),
          set: why.priority.set.map(pri).join(", "),
        })}
      </p>
      {hint && <p>{t("chat.agent.whyHint", { text: hint.text })}</p>}
      <h5 className="font-semibold text-fg-1">{t("explain.neighborsTitle")}</h5>
      {why.neighbors.length === 0 ? (
        <p>{t("explain.neighborsNone")}</p>
      ) : (
        <ul className="flex list-disc flex-col gap-1 ps-5">
          {why.neighbors.map((n, i) => (
            <li key={i}>
              <span dir={textDir(n.text)}>{n.text}</span>
              {" ("}
              {t("explain.neighborSim", { pct: Math.round(n.sim * 100) })}
              {", "}
              {SOURCES.has(n.source) ? t(`explain.source.${n.source}` as DictKey) : n.source}
              {")"}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

/** Props for {@link ProposalCard}. */
export interface ProposalCardProps {
  proposal: ProposalOut;
  busy: boolean;
  onConfirm: () => void;
  onDecline: () => void;
  /** A clarifying chip was chosen: the option id. */
  onAnswer: (optionId: string) => void;
}

/**
 * The suggestion the student approves: department, priority as a plain word, the action, and two
 * buttons. A FAQ answer is shown inside, with "Record a request anyway" instead of "Yes, send it".
 * Nothing is created until the student confirms.
 */
export function ProposalCard({ proposal, busy, onConfirm, onDecline, onAnswer }: ProposalCardProps) {
  const t = useT();
  const { lang } = useLang();
  const officeLabel = useOfficeLabel();
  const faq = proposal.action_kind === "faq_answer" ? proposal.faq : null;
  const action: DictKey =
    proposal.action_kind === "safety_alert" ? "chat.agent.actionSafety" : faq ? "chat.agent.actionFaq" : "chat.agent.actionTicket";
  const q = proposal.question;
  return (
    <section aria-label={t("chat.agent.cardTitle")} className="flex max-w-prose flex-col gap-3 rounded-lg border border-line bg-surface-1 p-4 shadow-1">
      <h2 className="text-lg font-semibold text-fg-1">{t("chat.agent.cardTitle")}</h2>
      <p dir={textDir(proposal.text)} className="text-fg-2">
        {proposal.text}
      </p>
      <ul className="flex flex-col gap-1 text-fg-1">
        <li>{t("chat.agent.office", { office: officeLabel(proposal.office) })}</li>
        <li>{t("chat.agent.priority", { priority: labelOf("priority", proposal.priority, lang) })}</li>
        <li>{t(action)}</li>
      </ul>
      {faq && (
        <div className="flex flex-col gap-1 rounded-md bg-surface-2 p-3">
          <h3 className="text-sm font-semibold text-fg-1">{t("chat.agent.faqTitle")}</h3>
          <p dir={textDir(faq.question)} className="font-medium text-fg-1">
            {faq.question}
          </p>
          <p dir={textDir(faq.answer)} className="text-fg-2">
            {faq.answer}
          </p>
        </div>
      )}
      {q && (
        <div className="flex flex-col gap-2">
          <p dir={textDir(q.text)} className="font-medium text-fg-1">
            {q.text}
          </p>
          <ChipGroup
            label={t("chat.clarifyGroup")}
            items={q.options.map((o) => ({ id: o.id, label: o.label, disabled: busy }))}
            value={null}
            onChange={onAnswer}
          />
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        <Button variant={faq ? "secondary" : "primary"} loading={busy} onClick={onConfirm}>
          {faq ? t("chat.agent.recordAnyway") : t("chat.agent.yes")}
        </Button>
        <Button variant="secondary" disabled={busy} onClick={onDecline}>
          {t("chat.agent.notNow")}
        </Button>
      </div>
      <Why>
        <WhyDetails proposal={proposal} />
      </Why>
    </section>
  );
}

/** Props for {@link RecordedCard}. */
export interface RecordedCardProps {
  ticketId: string | null;
  triage: TriageResponse | null;
  /** The suggestion the student approved: its numbers appear under "Why this?". */
  proposal: ProposalOut | null;
}

/** "Request recorded #AB12CD34" with a link to the request, and "Why this?" with the counterfactual hint. */
export function RecordedCard({ ticketId, triage, proposal }: RecordedCardProps) {
  const t = useT();
  const [view, setView] = useState<CounterfactualView | null>(null);
  const hint = triage?.explanation?.counterfactual ?? null;
  const requestId = triage?.request_id ?? null;
  const tryDrop = async (token: string) => {
    if (!requestId) return;
    const res = await fetchCounterfactual(requestId, token);
    if (res.ok) setView(res.data);
  };
  const hasWhy = proposal !== null || hint !== null;
  return (
    <section role="status" className="flex max-w-prose flex-col gap-3 rounded-lg border-2 border-ok bg-surface-1 p-4">
      <h2 className="text-lg font-semibold text-fg-1">
        {ticketId ? t("chat.agent.recordedNumber", { number: ticketId.replace(/-/g, "").slice(0, 8).toUpperCase() }) : t("chat.agent.recorded")}
      </h2>
      <p className="text-sm text-fg-2">{t("chat.agent.recordedDemo")}</p>
      {ticketId && (
        <div>
          <Link href={`/requests/${encodeURIComponent(ticketId)}`} className="font-semibold text-accent underline">
            {t("chat.agent.view")}
          </Link>
        </div>
      )}
      {hasWhy && (
        <Why>
          {proposal && <WhyDetails proposal={proposal} />}
          <CounterfactualHint hint={hint} view={view} onCounterfactual={(token) => void tryDrop(token)} />
        </Why>
      )}
    </section>
  );
}
