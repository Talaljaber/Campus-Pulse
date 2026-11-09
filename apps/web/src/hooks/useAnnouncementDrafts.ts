"use client";

import { useCallback, useEffect, useState } from "react";
import type { AiResult } from "@/lib/ai/result";
import { dismissDraft, editDraft, listDrafts, publishDraft, type AnnouncementDraft } from "@/lib/announcements/drafts";

/** `ok`, a stale version (`conflict`, HTTP 409), or any other failure. */
export type DraftOutcome = "ok" | "conflict" | "failed";

/**
 * The pending suggested announcements. Edit keeps the draft in the list with its new version; publish
 * and dismiss take it out. A failed load just shows nothing (the section is optional).
 */
export function useAnnouncementDrafts() {
  const [drafts, setDrafts] = useState<AnnouncementDraft[]>([]);

  useEffect(() => {
    let live = true;
    void listDrafts().then((res) => {
      if (live && res.ok) setDrafts(res.data.filter((d) => d.status === "pending"));
    });
    return () => {
      live = false;
    };
  }, []);

  const apply = useCallback((res: AiResult<AnnouncementDraft>, id: string, keep: boolean): DraftOutcome => {
    if (!res.ok) return res.status === 409 ? "conflict" : "failed";
    const next = res.data;
    setDrafts((cur) => (keep ? cur.map((d) => (d.id === id ? next : d)) : cur.filter((d) => d.id !== id)));
    return "ok";
  }, []);

  const edit = useCallback(
    async (d: AnnouncementDraft, title: string, body: string) => apply(await editDraft(d.id, d.version, title, body), d.id, true),
    [apply],
  );
  /** Publishes what is on screen: unsaved edits are saved first (with the version that save returns). */
  const publish = useCallback(
    async (d: AnnouncementDraft, title: string, body: string): Promise<DraftOutcome> => {
      let version = d.version;
      if (title.trim() !== d.title || body.trim() !== d.body) {
        const saved = await editDraft(d.id, d.version, title, body);
        if (!saved.ok) return saved.status === 409 ? "conflict" : "failed";
        version = saved.data.version;
      }
      return apply(await publishDraft(d.id, version), d.id, false);
    },
    [apply],
  );
  const dismiss = useCallback(async (d: AnnouncementDraft) => apply(await dismissDraft(d.id, d.version), d.id, false), [apply]);

  return { drafts, edit, publish, dismiss };
}
