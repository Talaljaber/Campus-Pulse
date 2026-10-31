"use client";

import { useEffect, useRef } from "react";
import { noticeFromNotification } from "@/lib/chat/service";
import type { NoticeData } from "@/lib/chat/types";
import { subscribeNotifications } from "@/lib/repos/notifications";
import { createBrowserSupabase } from "@/lib/supabase/browser";

/**
 * Subscribes the student to their own `notifications` (the only table a student listens
 * to) and reports each new row as a notice. Unsubscribes on unmount. A missing alias or
 * a failed subscription simply means no live updates; the page keeps working.
 */
export function useNotifications(alias: string | null, onNotice: (n: NoticeData) => void): void {
  const handler = useRef(onNotice);
  useEffect(() => {
    handler.current = onNotice;
  }, [onNotice]);

  useEffect(() => {
    if (!alias) return;
    try {
      return subscribeNotifications(createBrowserSupabase(), alias, (row) => handler.current(noticeFromNotification(row)));
    } catch {
      return undefined;
    }
  }, [alias]);
}
