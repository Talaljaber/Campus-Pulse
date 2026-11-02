"use client";

import { useCallback } from "react";
import { useT } from "@/i18n";
import { useToast } from "@/components/ui/Toast";
import { openFile } from "@/lib/files/service";

/** Returns `open(fileId)`: fetches a 60-second signed link, opens it in a new tab, toasts a sentence on failure. */
export function useFileOpener(): (fileId: string) => Promise<void> {
  const t = useT();
  const toast = useToast();
  return useCallback(
    async (fileId: string) => {
      const res = await openFile(fileId);
      if (!res.ok) toast.show(t("files.error.open"), "danger");
    },
    [t, toast],
  );
}
