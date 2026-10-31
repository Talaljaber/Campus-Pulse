import { ar } from "./ar";
import { en, type Dict } from "./en";

export type Lang = "en" | "ar";
export const LANGS: readonly Lang[] = ["en", "ar"];
export const LANG_COOKIE = "cp_lang";

/** Union of dotted leaf keys of a nested string dictionary, e.g. `"ui.table.empty"`. */
export type FlatKeys<T, P extends string = ""> = {
  [K in keyof T & string]: T[K] extends string ? `${P}${K}` : FlatKeys<T[K], `${P}${K}.`>;
}[keyof T & string];

export type DictKey = FlatKeys<Dict>;

export const dictionaries: Record<Lang, Dict> = { en, ar };

export function dirOf(lang: Lang): "ltr" | "rtl" {
  return lang === "ar" ? "rtl" : "ltr";
}

export function isLang(v: unknown): v is Lang {
  return v === "en" || v === "ar";
}

/** Flatten a nested dictionary into dotted keys. */
export function flatten(d: object, prefix = ""): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(d)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (typeof v === "string") out[key] = v;
    else Object.assign(out, flatten(v as object, key));
  }
  return out;
}

const flat: Record<Lang, Record<string, string>> = { en: flatten(en), ar: flatten(ar) };

/** Translate `key` for `lang`, substituting `{name}` placeholders. Falls back to English. */
export function translate(lang: Lang, key: DictKey, vars?: Record<string, string | number>): string {
  const template = flat[lang][key] ?? flat.en[key] ?? key;
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (m, name: string) => (name in vars ? String(vars[name]) : m));
}

/**
 * Pick the language: cookie first, then `Accept-Language` (first supported tag
 * wins), then English.
 */
export function resolveLang(cookie: string | undefined | null, acceptLanguage: string | undefined | null): Lang {
  if (isLang(cookie)) return cookie;
  if (acceptLanguage) {
    const tags = acceptLanguage
      .split(",")
      .map((part) => {
        const [tag = "", q] = part.trim().split(";q=");
        return { base: tag.toLowerCase().split("-")[0] ?? "", q: q ? Number(q) : 1 };
      })
      .sort((a, b) => b.q - a.q);
    for (const t of tags) if (isLang(t.base)) return t.base;
  }
  return "en";
}

const CATEGORY_KEYS = {
  Registration: "category.registration",
  "IT Support": "category.itSupport",
  Finance: "category.finance",
  Transportation: "category.transportation",
  Facilities: "category.facilities",
  "Academic Support": "category.academicSupport",
} as const satisfies Record<string, DictKey>;

const PRIORITY_KEYS = {
  low: "priority.low",
  medium: "priority.medium",
  high: "priority.high",
} as const satisfies Record<string, DictKey>;

export const CATEGORY_VALUES = Object.keys(CATEGORY_KEYS) as (keyof typeof CATEGORY_KEYS)[];
export const PRIORITY_VALUES = Object.keys(PRIORITY_KEYS) as (keyof typeof PRIORITY_KEYS)[];

/**
 * Display name for an exact backend label. Unknown values are returned unchanged so
 * a new backend label never renders blank.
 */
export function labelOf(kind: "category" | "priority", value: string, lang: Lang): string {
  const map: Record<string, DictKey> = kind === "category" ? CATEGORY_KEYS : PRIORITY_KEYS;
  const key = map[value];
  return key ? translate(lang, key) : value;
}
