"use client";

import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";
import { dirOf, translate, type DictKey, type Lang } from "./core";

export interface I18nValue {
  lang: Lang;
  dir: "ltr" | "rtl";
  /** Change language. A no-op inside a `LangScope`. */
  setLang: (lang: Lang) => void;
}

export const I18nContext = createContext<I18nValue>({ lang: "en", dir: "ltr", setLang: () => {} });

/** Current language, direction and setter. */
export function useLang(): I18nValue {
  return useContext(I18nContext);
}

/** Returns `t(key, vars?)` bound to the current language. Falls back to English without a provider. */
export function useT(): (key: DictKey, vars?: Record<string, string | number>) => string {
  const { lang } = useContext(I18nContext);
  return useCallback((key, vars) => translate(lang, key, vars), [lang]);
}

/**
 * Renders a subtree in a fixed language without touching `<html>`. Used by the
 * kitchen sink to show English and Arabic side by side.
 */
export function LangScope({ lang, children, className }: { lang: Lang; children: ReactNode; className?: string }) {
  const value = useMemo<I18nValue>(() => ({ lang, dir: dirOf(lang), setLang: () => {} }), [lang]);
  return (
    <I18nContext.Provider value={value}>
      <div lang={lang} dir={dirOf(lang)} className={className}>
        {children}
      </div>
    </I18nContext.Provider>
  );
}
