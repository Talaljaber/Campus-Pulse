"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { I18nContext, LANG_COOKIE, dirOf, type I18nValue, type Lang } from "@/i18n";

/** Props for {@link RtlProvider}. */
export interface RtlProviderProps {
  /** Initial language, resolved on the server from the `cp_lang` cookie then `Accept-Language`. */
  lang: Lang;
  children: ReactNode;
}

/**
 * Owns the app language. Keeps `<html lang dir>` in sync and persists the choice in
 * the `cp_lang` cookie (one year) so the server renders the right direction next time.
 */
export function RtlProvider({ lang: initial, children }: RtlProviderProps) {
  const [lang, setLangState] = useState<Lang>(initial);

  useEffect(() => {
    const root = document.documentElement;
    root.lang = lang;
    root.dir = dirOf(lang);
  }, [lang]);

  const setLang = useCallback((next: Lang) => {
    try {
      document.cookie = `${LANG_COOKIE}=${next}; path=/; max-age=31536000; samesite=lax`;
    } catch {
      // cookies blocked: the choice still applies for this session
    }
    setLangState(next);
  }, []);

  const value = useMemo<I18nValue>(() => ({ lang, dir: dirOf(lang), setLang }), [lang, setLang]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}
