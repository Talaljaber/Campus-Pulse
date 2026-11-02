"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useAgent } from "@/hooks/useAgent";
import { useLang, useT, type DictKey } from "@/i18n";
import type { Role } from "@/lib/auth/routing";
import type { AgentErrorKind, AgentMessage } from "@/lib/chat/agentReducer";
import { speechLangFor } from "@/lib/voice/speech";
import { textDir } from "../explain/text";
import { AppShell } from "../shell/AppShell";
import { PageHeader } from "../shell/PageHeader";
import { Button } from "../ui/Button";
import { cn } from "../ui/cn";
import { TextArea } from "../ui/TextField";
import { Composer } from "./Composer";
import { DistressCard } from "./DistressCard";
import { MicButton } from "./MicButton";
import { ProposalCard, RecordedCard } from "./ProposalCard";

const ERROR_KEY: Record<AgentErrorKind, DictKey> = {
  generic: "chat.errorGeneric",
  waking: "chat.errorWaking",
  session: "chat.errorSession",
  expired: "chat.agent.errorExpired",
};

/** A plain message bubble. The student's sits at the start edge in the accent colour, the assistant's in grey. */
function Bubble({ message }: { message: AgentMessage }) {
  const t = useT();
  const mine = message.role === "user";
  return (
    <li className={cn("flex flex-col gap-1", mine ? "items-end" : "items-start")}>
      <span className="text-xs text-fg-3">{mine ? t("chat.you") : t("chat.agent.assistant")}</span>
      <p
        dir={textDir(message.content)}
        className={cn(
          "max-w-prose whitespace-pre-wrap rounded-lg px-3 py-2",
          mine ? "bg-accent text-on-accent" : "bg-surface-2 text-fg-1",
        )}
      >
        {message.content}
      </p>
    </li>
  );
}

/** The plain form used when the assistant is not available: type, "Check", then the same card. */
function FallbackForm({ initial, busy, onCheck }: { initial: string; busy: boolean; onCheck: (text: string) => void }) {
  const t = useT();
  const [text, setText] = useState(initial);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!busy && text.trim()) onCheck(text.trim());
  };
  return (
    <form onSubmit={submit} className="flex flex-col gap-2">
      <p className="text-sm text-fg-2">{t("chat.agent.fallbackNote")}</p>
      <TextArea label={t("chat.agent.formLabel")} value={text} onChange={(e) => setText(e.target.value)} rows={3} dir="auto" />
      <div>
        <Button type="submit" loading={busy} disabled={text.trim() === ""}>
          {t("chat.agent.check")}
        </Button>
      </div>
    </form>
  );
}

/** Props for {@link AgentScreen}. */
export interface AgentScreenProps {
  alias: string | null;
  /** The signed-in role. Staff and admins use the agent too; default student. */
  role?: Role;
}

/**
 * The ask page `/ask`: a short conversation with the assistant. It suggests where a request goes (a
 * proposal card) and the student confirms; nothing is created before that. When the assistant is not
 * available it shows a plain form that uses the same card.
 */
export function AgentScreen({ alias, role = "student" }: AgentScreenProps) {
  const t = useT();
  const { lang } = useLang();
  const agent = useAgent({ recorded: t("chat.agent.recorded"), declined: t("chat.agent.declined") });
  const endRef = useRef<HTMLDivElement>(null);
  const fallback = agent.mode === "fallback";
  const count = agent.messages.length;

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [count, agent.proposal]);

  return (
    <AppShell role={role} current="ask" alias={alias} width="narrow">
      <PageHeader title={t("chat.title")} subtitle={t("app.tagline")} />
      <p className="rounded-md bg-surface-2 px-3 py-2 text-sm text-fg-2">{t("chat.agent.demo")}</p>

      <div className="flex-1">
        <ol aria-label={t("chat.thread")} className="flex flex-col gap-4 py-4">
          {agent.messages.length === 0 && !fallback && <li className="text-fg-2">{t("chat.agent.welcome")}</li>}
          {agent.messages.map((m) =>
            m.triage?.status === "distress" ? (
              <li key={m.id}>
                <DistressCard message={m.triage.message ?? m.content} />
              </li>
            ) : m.kind === "ticket" ? (
              <li key={m.id}>
                <RecordedCard ticketId={m.ticketId ?? null} triage={m.triage ?? null} proposal={m.proposal ?? null} />
              </li>
            ) : (
              <Bubble key={m.id} message={m} />
            ),
          )}
          {agent.proposal && (
            <li>
              <ProposalCard
                proposal={agent.proposal}
                busy={agent.busy}
                onConfirm={() => void agent.confirm()}
                onDecline={agent.decline}
                onAnswer={(option) => void agent.answer(option)}
              />
            </li>
          )}
        </ol>
        {agent.error && (
          <p role="alert" className="rounded-md border border-danger px-3 py-2 text-fg-1">
            {t(ERROR_KEY[agent.error])}
          </p>
        )}
        <div ref={endRef} />
      </div>

      <div className="sticky bottom-0 flex flex-col gap-3 border-t border-line bg-surface-0 pb-2 pt-3">
        {fallback ? (
          <FallbackForm key={count} initial={agent.messages[count - 1]?.role === "user" ? agent.draft : ""} busy={agent.busy} onCheck={(text) => void agent.check(text)} />
        ) : (
          <Composer
            busy={agent.busy}
            onSubmit={(text) => void agent.send(text)}
            micSlot={(mic) => <MicButton lang={speechLangFor(lang)} onStart={mic.begin} onTranscript={mic.apply} disabled={agent.busy} />}
          />
        )}
      </div>
    </AppShell>
  );
}
