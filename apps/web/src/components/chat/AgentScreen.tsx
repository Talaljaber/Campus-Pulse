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
import { Icon } from "../ui/Icon";
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
          "max-w-[85%] whitespace-pre-wrap rounded-2xl px-3 py-2 shadow-1 sm:max-w-[72%]",
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
  /** The name for the header greeting: the display name, else the alias. */
  name?: string | null;
  /** The signed-in role. Staff and admins use the agent too; default student. */
  role?: Role;
}

/**
 * The ask page `/ask`: a short conversation with the assistant. It suggests where a request goes (a
 * proposal card) and the student confirms; nothing is created before that. When the assistant is not
 * available it shows a plain form that uses the same card.
 */
export function AgentScreen({ alias, name, role = "student" }: AgentScreenProps) {
  const t = useT();
  const { lang } = useLang();
  const agent = useAgent({ recorded: t("chat.agent.recorded"), declined: t("chat.agent.declined") });
  const threadRef = useRef<HTMLDivElement>(null);
  const fallback = agent.mode === "fallback";
  const count = agent.messages.length;
  const [starter, setStarter] = useState("");

  useEffect(() => {
    const thread = threadRef.current;
    if (!thread) return;
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (typeof thread.scrollTo === "function") {
      thread.scrollTo({ top: thread.scrollHeight, behavior: reduced ? "auto" : "smooth" });
    } else {
      thread.scrollTop = thread.scrollHeight;
    }
  }, [count, agent.proposal]);

  const chooseStarter = (text: string) => {
    setStarter("");
    requestAnimationFrame(() => setStarter(text));
  };

  return (
    <AppShell role={role} current="ask" name={name} alias={alias} workspace>
      <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-line bg-surface-1 shadow-card">
        <div className="shrink-0 border-b border-line bg-surface-raised px-4 py-3 sm:px-6 sm:py-4">
          <PageHeader title={t("chat.title")} subtitle={t("app.tagline")} />
          <p className="mt-3 rounded-md bg-surface-2 px-3 py-2 text-sm text-fg-2">{t("chat.agent.demo")}</p>
        </div>

        <div ref={threadRef} className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-4 sm:px-6" aria-label={t("chat.thread")}>
          <ol role="log" className="mx-auto flex w-full max-w-5xl flex-col gap-4" aria-live="polite">
          {agent.messages.length === 0 && !fallback && (
            <li className="mx-auto flex w-full max-w-xl flex-col items-center gap-3 rounded-lg border border-line bg-surface-raised p-5 text-center shadow-1">
              <span className="grid size-11 place-items-center rounded-full bg-surface-soft text-accent"><Icon name="chat" size={22} /></span>
              <p className="text-fg-2">{t("chat.agent.welcome")}</p>
              <div className="flex flex-wrap justify-center gap-2">
                {([t("chat.agent.starterWifi"), t("chat.agent.starterRegistration"), t("chat.agent.starterTransport")] as const).map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => chooseStarter(prompt)}
                    className="min-h-11 rounded-full border border-line bg-surface-0 px-3 text-sm font-medium text-accent transition-colors hover:bg-surface-soft"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </li>
          )}
          {agent.messages.map((m) =>
            m.distress || m.triage?.status === "distress" ? (
              <li key={m.id}>
                <DistressCard message={m.triage?.message ?? m.content} />
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
            <p role="alert" className="mx-auto mt-3 w-full max-w-5xl rounded-md border border-danger bg-surface-raised px-3 py-2 text-fg-1">
              {t(ERROR_KEY[agent.error])}
            </p>
          )}
        </div>

      <div className="shrink-0 border-t border-line bg-surface-raised p-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] shadow-float sm:px-6">
        {fallback ? (
          <FallbackForm key={count} initial={agent.messages[count - 1]?.role === "user" ? agent.draft : ""} busy={agent.busy} onCheck={(text) => void agent.check(text)} />
        ) : (
          <Composer
            busy={agent.busy}
            initialText={starter}
            onSubmit={(text) => void agent.send(text)}
            micSlot={(mic) => <MicButton lang={speechLangFor(lang)} onStart={mic.begin} onTranscript={mic.apply} disabled={agent.busy} />}
          />
        )}
      </div>
      </section>
    </AppShell>
  );
}
