"use client";

import { useId } from "react";
import { useLang, useT } from "@/i18n";

/** The slice of a `buildings` row the picker needs. */
export interface PickableBuilding {
  id: string;
  code: string;
  name_en: string;
  name_ar: string;
}

/** Props for {@link BuildingPicker}. */
export interface BuildingPickerProps {
  buildings: readonly PickableBuilding[];
  /** The chosen building id, or `null` for "no building". */
  value: string | null;
  onChange: (id: string | null) => void;
  disabled?: boolean;
}

/** Optional "where are you?" selector. A native select, so keyboard and screen readers work with no extra code. */
export function BuildingPicker({ buildings, value, onChange, disabled }: BuildingPickerProps) {
  const t = useT();
  const { lang } = useLang();
  const id = useId();
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-fg-1">
        {t("chat.building")}
      </label>
      <select
        id={id}
        value={value ?? ""}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value || null)}
        className="min-h-11 w-full rounded-md border border-line-strong bg-surface-0 px-3 text-base text-fg-1 disabled:opacity-55"
      >
        <option value="">{t("chat.noBuilding")}</option>
        {buildings.map((b) => (
          <option key={b.id} value={b.id}>
            {`${b.code} · ${lang === "ar" ? b.name_ar : b.name_en}`}
          </option>
        ))}
      </select>
    </div>
  );
}
