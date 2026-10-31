"use client";

import { useEffect, useState } from "react";
import { listBuildings } from "@/lib/repos/requests";
import { createBrowserSupabase } from "@/lib/supabase/browser";

export interface BuildingOption {
  id: string;
  code: string;
  name_en: string;
  name_ar: string;
}

/** The campus buildings for the optional location picker. A failed read gives an empty list (the picker hides). */
export function useBuildings(): BuildingOption[] {
  const [buildings, setBuildings] = useState<BuildingOption[]>([]);
  useEffect(() => {
    let live = true;
    listBuildings(createBrowserSupabase())
      .then((rows) => {
        if (live) setBuildings(rows.map(({ id, code, name_en, name_ar }) => ({ id, code, name_en, name_ar })));
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, []);
  return buildings;
}
