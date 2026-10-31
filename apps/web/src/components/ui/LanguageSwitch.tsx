"use client";

import { LANGS, translate, useLang, useT, type Lang } from "@/i18n";

/** Props for {@link LanguageSwitch}. */
export interface LanguageSwitchProps {
  className?: string;
}

/**
 * Two-button language toggle (English / Arabic). Each button is named in its own
 * language so it is recognisable regardless of the current UI language. `aria-pressed`
 * marks the active one.
 */
export function LanguageSwitch({ className = "" }: LanguageSwitchProps) {
  const { lang, setLang } = useLang();
  const t = useT();
  return (
    <div role="group" aria-label={t("lang.label")} className={`inline-flex rounded-md border border-accent p-0.5 ${className}`}>
      {LANGS.map((l: Lang) => {
        // Each language is named in itself, from the dictionary of that language.
        const name = translate(l, l === "en" ? "lang.en" : "lang.ar");
        const active = l === lang;
        return (
          <button
            key={l}
            type="button"
            lang={l}
            aria-pressed={active}
            aria-label={t("lang.switchTo", { name })}
            onClick={() => setLang(l)}
            className={`min-h-9 rounded-sm px-3 text-sm font-semibold transition-colors duration-(--cp-motion-fast) ${
              active ? "bg-accent text-on-accent" : "text-accent hover:bg-surface-2"
            }`}
          >
            {name}
          </button>
        );
      })}
    </div>
  );
}
