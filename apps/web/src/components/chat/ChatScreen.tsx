"use client";

import { useState } from "react";
import { useBuildings } from "@/hooks/useBuildings";
import { useChat } from "@/hooks/useChat";
import { useNotifications } from "@/hooks/useNotifications";
import { useLang, useT } from "@/i18n";
import { speechLangFor } from "@/lib/voice/speech";
import { AppShell } from "../shell/AppShell";
import { PageHeader } from "../shell/PageHeader";
import { BuildingPicker } from "./BuildingPicker";
import { ChatThread } from "./ChatThread";
import { Composer } from "./Composer";
import { MicButton } from "./MicButton";
import { Disclaimer } from "./Disclaimer";

/** Props for {@link ChatScreen}. */
export interface ChatScreenProps {
  /** The signed-in student's alias, from their profile. It scopes the live notifications. */
  alias: string | null;
}

/**
 * The student page `/`: header, conversation, optional building and the composer. It only
 * wires the `useChat`, `useNotifications` and `useBuildings` hooks to presentational parts.
 */
export function ChatScreen({ alias }: ChatScreenProps) {
  const t = useT();
  const { lang } = useLang();
  const chat = useChat();
  const buildings = useBuildings();
  const [building, setBuilding] = useState<string | null>(null);
  useNotifications(alias, chat.notice);

  return (
    <AppShell role="student" current="request" alias={alias} width="narrow">
      <PageHeader title={t("chat.title")} subtitle={t("app.tagline")} />

      <div className="flex-1">
        <ChatThread
          items={chat.items}
          counterfactuals={chat.counterfactuals}
          busy={chat.busy}
          onPick={(itemId, optionId) => void chat.pick(itemId, optionId)}
          onCounterfactual={(requestId, token) => void chat.counterfactual(requestId, token)}
        />
      </div>

      <div className="sticky bottom-0 flex flex-col gap-3 border-t border-line bg-surface-0 pb-2 pt-3">
        {buildings.length > 0 && <BuildingPicker buildings={buildings} value={building} onChange={setBuilding} disabled={chat.busy} />}
        <Composer
          busy={chat.busy}
          onSubmit={(text, mode) => void chat.send(text, mode, building)}
          micSlot={(mic) => <MicButton lang={speechLangFor(lang)} onStart={mic.begin} onTranscript={mic.apply} disabled={chat.busy} />}
        />
        <Disclaimer />
      </div>
    </AppShell>
  );
}
