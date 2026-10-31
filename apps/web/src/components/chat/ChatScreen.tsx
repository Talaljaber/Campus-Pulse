"use client";

import { useState } from "react";
import { useBuildings } from "@/hooks/useBuildings";
import { useChat } from "@/hooks/useChat";
import { useNotifications } from "@/hooks/useNotifications";
import { useSignOut } from "@/hooks/useSignIn";
import { useT } from "@/i18n";
import { Button } from "../ui/Button";
import { LanguageSwitch } from "../ui/LanguageSwitch";
import { BuildingPicker } from "./BuildingPicker";
import { ChatThread } from "./ChatThread";
import { Composer } from "./Composer";
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
  const chat = useChat();
  const buildings = useBuildings();
  const signOut = useSignOut();
  const [building, setBuilding] = useState<string | null>(null);
  useNotifications(alias, chat.notice);

  return (
    <main className="mx-auto flex min-h-dvh max-w-3xl flex-col gap-4 p-4 sm:p-6">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold">{t("chat.title")}</h1>
        <div className="flex items-center gap-2">
          <LanguageSwitch />
          <Button variant="ghost" size="sm" onClick={() => void signOut()}>
            {t("auth.signOut")}
          </Button>
        </div>
      </header>

      <p className="text-fg-2">{t("app.tagline")}</p>

      <div className="flex-1">
        <ChatThread
          items={chat.items}
          counterfactuals={chat.counterfactuals}
          busy={chat.busy}
          onPick={(itemId, optionId) => void chat.pick(itemId, optionId)}
          onCounterfactual={(requestId, token) => void chat.counterfactual(requestId, token)}
        />
      </div>

      <div className="sticky bottom-0 flex flex-col gap-3 bg-surface-0 pb-2 pt-3">
        {buildings.length > 0 && <BuildingPicker buildings={buildings} value={building} onChange={setBuilding} disabled={chat.busy} />}
        <Composer busy={chat.busy} onSubmit={(text, mode) => void chat.send(text, mode, building)} />
        <Disclaimer />
      </div>
    </main>
  );
}
