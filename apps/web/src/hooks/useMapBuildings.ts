"use client";

import { useEffect, useState } from "react";
import type { Building } from "@/components/pulse/map/campus";
import { listBuildings } from "@/lib/repos/requests";
import { createBrowserSupabase } from "@/lib/supabase/browser";

/**
 * The campus buildings with their map coordinates, for the Pulse map and for naming a
 * building. A failed read gives an empty list: the page still works, the map is just bare.
 */
export function useMapBuildings(): Building[] {
  const [buildings, setBuildings] = useState<Building[]>([]);
  useEffect(() => {
    let live = true;
    try {
      listBuildings(createBrowserSupabase())
        .then((rows) => live && setBuildings(rows))
        .catch(() => {});
    } catch {
      // No Supabase client: leave the list empty.
    }
    return () => {
      live = false;
    };
  }, []);
  return buildings;
}
