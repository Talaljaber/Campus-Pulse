"use client";

import { useState } from "react";
import { labelOf, useLang, useT, type DictKey } from "@/i18n";
import type { TicketView } from "@/lib/staff/tickets";
import { isRunning } from "@/lib/tickets/clock";
import { staffStatusOptions, type StaffStatus } from "@/lib/tickets/transitions";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { Select } from "../ui/Select";
import { TextArea } from "../ui/TextField";
import { ForwardForm } from "./ForwardForm";

/** Props for {@link TicketSidePanel}. Each action resolves true when it worked (so the form can reset). */
export interface TicketSidePanelProps {
  ticket: Pick<TicketView, "status" | "priority" | "office">;
  busy: boolean;
  onStatus: (status: StaffStatus, note: string) => Promise<boolean>;
  onForward: (office: string, note: string) => Promise<boolean>;
  onPriority: (priority: "low" | "medium" | "high", note: string) => Promise<boolean>;
}

const PRIORITIES = ["low", "medium", "high"] as const;

/** The workspace's side panel: change status, forward to another office, change priority (each with an optional note). */
export function TicketSidePanel({ ticket, busy, onStatus, onForward, onPriority }: TicketSidePanelProps) {
  const t = useT();
  const { lang } = useLang();
  const statuses = staffStatusOptions(ticket.status);
  const running = isRunning(ticket.status);

  const [status, setStatus] = useState("");
  const [statusNote, setStatusNote] = useState("");
  const [priority, setPriority] = useState("");
  const [priorityNote, setPriorityNote] = useState("");
  const [forwarding, setForwarding] = useState(false);

  if (statuses.length === 0) {
    return (
      <Card title={t("workspace.actions")}>
        <p className="text-sm text-fg-2">{t("workspace.noActions")}</p>
      </Card>
    );
  }

  const reopening = ticket.status === "solved" || ticket.status === "closed";
  const priorities = PRIORITIES.filter((p) => p !== ticket.priority);

  return (
    <div className="flex flex-col gap-4">
      <Card title={t("workspace.statusTitle")}>
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (!status || busy) return;
            void onStatus(status as StaffStatus, statusNote).then((ok) => {
              if (ok) {
                setStatus("");
                setStatusNote("");
              }
            });
          }}
        >
          <Select
            label={t("workspace.statusLabel")}
            value={status}
            disabled={busy}
            onChange={(e) => setStatus(e.target.value)}
            options={[{ value: "", label: t("workspace.choose") }, ...statuses.map((s) => ({ value: s, label: t(`staff.status.${s}` as DictKey) }))]}
          />
          <TextArea label={t("workspace.note")} value={statusNote} disabled={busy} rows={2} maxLength={4000} onChange={(e) => setStatusNote(e.target.value)} />
          <div>
            <Button type="submit" loading={busy} disabled={!status}>
              {t(reopening ? "workspace.reopen" : "workspace.changeStatus")}
            </Button>
          </div>
        </form>
      </Card>

      {running && (
        <Card title={t("workspace.forwardTitle")}>
          {forwarding ? (
            <ForwardForm
              initialOffice={ticket.office}
              exclude={[ticket.office]}
              busy={busy}
              onSubmit={(office, note) => void onForward(office, note).then((ok) => ok && setForwarding(false))}
              onCancel={() => setForwarding(false)}
            />
          ) : (
            <Button variant="secondary" onClick={() => setForwarding(true)}>
              {t("forward.ticketButton")}
            </Button>
          )}
        </Card>
      )}

      {running && (
        <Card title={t("workspace.priorityTitle")}>
          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              if (!priority || busy) return;
              void onPriority(priority as (typeof PRIORITIES)[number], priorityNote).then((ok) => {
                if (ok) {
                  setPriority("");
                  setPriorityNote("");
                }
              });
            }}
          >
            <p className="text-sm text-fg-2">{t("workspace.priorityHint", { priority: labelOf("priority", ticket.priority, lang) })}</p>
            <Select
              label={t("workspace.priorityLabel")}
              value={priority}
              disabled={busy}
              onChange={(e) => setPriority(e.target.value)}
              options={[{ value: "", label: t("workspace.choose") }, ...priorities.map((p) => ({ value: p, label: labelOf("priority", p, lang) }))]}
            />
            <TextArea label={t("workspace.note")} value={priorityNote} disabled={busy} rows={2} maxLength={4000} onChange={(e) => setPriorityNote(e.target.value)} />
            <div>
              <Button type="submit" loading={busy} disabled={!priority}>
                {t("workspace.changePriority")}
              </Button>
            </div>
          </form>
        </Card>
      )}
    </div>
  );
}
