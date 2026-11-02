"use client";

import { useCallback, useEffect, useState } from "react";
import { applyChange, sortNewest } from "@/lib/announcements/view";
import {
  listLiveAnnouncements,
  listOfficeAnnouncements,
  subscribeAnnouncements,
  type AnnouncementRow,
} from "@/lib/repos/announcements";
import { createBrowserSupabase } from "@/lib/supabase/browser";
import type { LoadState } from "./useTicketQueue";

/**
 * The live announcements for Home: read once, then kept current with Realtime inserts and updates
 * (a new notice appears, an archived or ended one disappears). A failed subscription only means no
 * live updates; a failed read shows the retry state.
 */
export function useLiveAnnouncements() {
  const [rows, setRows] = useState<AnnouncementRow[]>([]);
  const [load, setLoad] = useState<LoadState>("loading");
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let live = true;
    let off: (() => void) | undefined;
    try {
      const sb = createBrowserSupabase();
      listLiveAnnouncements(sb, new Date())
        .then((list) => {
          if (!live) return;
          setRows((cur) => cur.reduce((acc, r) => applyChange(acc, r, new Date()), list));
          setLoad("ready");
        })
        .catch(() => {
          if (live) setLoad("error");
        });
      off = subscribeAnnouncements(sb, (row) => setRows((cur) => applyChange(cur, row, new Date())));
    } catch {
      queueMicrotask(() => live && setLoad("error"));
    }
    return () => {
      live = false;
      off?.();
    };
  }, [nonce]);

  const reload = useCallback(() => {
    setLoad("loading");
    setNonce((n) => n + 1);
  }, []);

  return { rows, load, reload };
}

/**
 * The announcements a staff member manages (their office; every office for an admin), archived ones
 * included, newest first. `put` folds in the row an API call returned so the table updates at once,
 * before Realtime delivers the same row.
 */
export function useManagedAnnouncements(office: string | null) {
  const [rows, setRows] = useState<AnnouncementRow[]>([]);
  const [load, setLoad] = useState<LoadState>("loading");
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let live = true;
    let off: (() => void) | undefined;
    const mine = (r: AnnouncementRow) => office === null || r.office === office;
    const merge = (cur: AnnouncementRow[], row: AnnouncementRow) =>
      sortNewest([...cur.filter((r) => r.id !== row.id), row]);
    try {
      const sb = createBrowserSupabase();
      listOfficeAnnouncements(sb, office)
        .then((list) => {
          if (!live) return;
          setRows((cur) => cur.reduce(merge, sortNewest(list)));
          setLoad("ready");
        })
        .catch(() => {
          if (live) setLoad("error");
        });
      off = subscribeAnnouncements(sb, (row) => {
        if (mine(row)) setRows((cur) => merge(cur, row));
      });
    } catch {
      queueMicrotask(() => live && setLoad("error"));
    }
    return () => {
      live = false;
      off?.();
    };
  }, [office, nonce]);

  const put = useCallback(
    (row: AnnouncementRow) => setRows((cur) => sortNewest([...cur.filter((r) => r.id !== row.id), row])),
    [],
  );
  const reload = useCallback(() => {
    setLoad("loading");
    setNonce((n) => n + 1);
  }, []);

  return { rows, load, reload, put };
}
