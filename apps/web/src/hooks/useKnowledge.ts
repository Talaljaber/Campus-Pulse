"use client";

import { useCallback, useEffect, useState } from "react";
import { deleteKnowledge, listKnowledge, uploadKnowledge, type KnowledgeDoc, type KnowledgeInput } from "@/lib/knowledge/service";

export type KnowledgeLoad = "loading" | "ready" | "error";

/** The outcome of an add or a delete: `message` is the server's own text when it refused (a 422), else null. */
export type KnowledgeOutcome<T = undefined> = { ok: true; doc: T } | { ok: false; status: number; message: string | null };

/** The knowledge-base documents (admin), with add and delete. The new document goes on top of the list. */
export function useKnowledge() {
  const [docs, setDocs] = useState<KnowledgeDoc[]>([]);
  const [load, setLoad] = useState<KnowledgeLoad>("loading");

  useEffect(() => {
    let live = true;
    void listKnowledge().then((res) => {
      if (!live) return;
      if (res.ok) {
        setDocs(res.data.documents);
        setLoad("ready");
      } else setLoad("error");
    });
    return () => {
      live = false;
    };
  }, []);

  const add = useCallback(async (input: KnowledgeInput): Promise<KnowledgeOutcome<KnowledgeDoc>> => {
    const res = await uploadKnowledge(input);
    if (!res.ok) return { ok: false, status: res.status, message: res.status === 422 ? res.error : null };
    setDocs((cur) => [res.data, ...cur.filter((d) => d.id !== res.data.id)]);
    return { ok: true, doc: res.data };
  }, []);

  const remove = useCallback(async (id: string): Promise<KnowledgeOutcome> => {
    const res = await deleteKnowledge(id);
    if (!res.ok) return { ok: false, status: res.status, message: null };
    setDocs((cur) => cur.filter((d) => d.id !== id));
    return { ok: true, doc: undefined };
  }, []);

  return { docs, load, add, remove };
}
