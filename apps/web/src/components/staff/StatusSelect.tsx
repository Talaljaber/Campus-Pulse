"use client";

import { useT, type DictKey } from "@/i18n";
import type { TicketStatus } from "@/lib/ai/types";
import { SETTABLE_STATUSES } from "@/lib/staff/tickets";
import { Select } from "../ui/Select";

/** Props for {@link StatusSelect}. */
export interface StatusSelectProps {
  /** The ticket's current status (any string; an unknown one is shown as is and cannot be re-chosen). */
  value: string;
  onChange: (status: TicketStatus) => void;
  /** Accessible name, e.g. "Status of Wi-Fi outage". */
  label: string;
  /** A change is being saved: the control is disabled. */
  pending?: boolean;
  className?: string;
}

const KNOWN = new Set<string>([...SETTABLE_STATUSES, "merged"]);

/**
 * Status picker for one ticket. `merged` is set by the system when a ticket joins an incident,
 * so it is shown when current but staff cannot pick it, and a merged ticket's picker is disabled.
 */
export function StatusSelect({ value, onChange, label, pending = false, className }: StatusSelectProps) {
  const t = useT();
  const name = (s: string) => (KNOWN.has(s) ? t(`staff.status.${s}` as DictKey) : s);
  const options: { value: string; label: string }[] = SETTABLE_STATUSES.map((s) => ({ value: s, label: name(s) }));
  if (!options.some((o) => o.value === value)) options.push({ value, label: name(value) });
  return (
    <Select
      label={label}
      hideLabel
      value={value}
      options={options}
      disabled={pending || value === "merged"}
      aria-busy={pending || undefined}
      onChange={(e) => onChange(e.target.value as TicketStatus)}
      className={className}
    />
  );
}
