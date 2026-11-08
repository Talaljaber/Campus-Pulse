"use client";

import { useT } from "@/i18n";
import type { ChatTicketOut } from "@/lib/chat/agentTypes";
import { Button } from "../ui/Button";
import { StatusCard } from "./StatusCard";

/** Props for {@link WithdrawCard}. */
export interface WithdrawCardProps {
  ticket: ChatTicketOut;
  busy: boolean;
  /** "Close it": the requester closes their own request. */
  onClose: () => void;
  /** "Keep it": nothing changes. */
  onKeep: () => void;
}

/** "Close request #n?" with the request's card. The assistant never closes anything itself: the button does. */
export function WithdrawCard({ ticket, busy, onClose, onKeep }: WithdrawCardProps) {
  const t = useT();
  const title = t("chat.card.closeTitle", { number: ticket.number });
  return (
    <section aria-label={title} className="flex max-w-prose flex-col gap-3 rounded-lg border border-line bg-surface-1 p-4 shadow-1">
      <h2 className="text-lg font-semibold text-fg-1">{title}</h2>
      <StatusCard ticket={ticket} />
      <div className="flex flex-wrap gap-2">
        <Button variant="danger" loading={busy} onClick={onClose}>
          {t("chat.card.closeIt")}
        </Button>
        <Button variant="secondary" disabled={busy} onClick={onKeep}>
          {t("chat.card.keepIt")}
        </Button>
      </div>
    </section>
  );
}
