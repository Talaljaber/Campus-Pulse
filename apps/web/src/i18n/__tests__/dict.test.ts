import { describe, expect, it } from "vitest";
import {
  CATEGORY_VALUES,
  PRIORITY_VALUES,
  ar,
  en,
  flatten,
  labelOf,
  resolveLang,
  translate,
} from "@/i18n";

describe("dictionaries", () => {
  it("ar has exactly the keys of en", () => {
    expect(Object.keys(flatten(ar)).sort()).toEqual(Object.keys(flatten(en)).sort());
  });

  it("no value is empty and placeholders match across languages", () => {
    const e = flatten(en);
    const a = flatten(ar);
    const ph = (s: string) => (s.match(/\{\w+\}/g) ?? []).sort().join();
    for (const k of Object.keys(e)) {
      expect(a[k]!.trim(), k).not.toBe("");
      expect(ph(a[k]!), k).toBe(ph(e[k]!));
    }
  });
});

describe("translate", () => {
  it("substitutes variables", () => {
    expect(translate("en", "devui.ticketsTab", { office: "IT" })).toBe("Tickets for IT");
    expect(translate("ar", "devui.ticketsTab", { office: "IT" })).toContain("IT");
  });
  it("leaves an unknown placeholder visible", () => {
    expect(translate("en", "lang.switchTo")).toContain("{name}");
  });
});

describe("labelOf", () => {
  it("round-trips all 9 backend labels in both languages", () => {
    expect(CATEGORY_VALUES).toHaveLength(6);
    expect(PRIORITY_VALUES).toHaveLength(3);
    for (const lang of ["en", "ar"] as const) {
      for (const c of CATEGORY_VALUES) expect(labelOf("category", c, lang).length).toBeGreaterThan(0);
      for (const p of PRIORITY_VALUES) expect(labelOf("priority", p, lang).length).toBeGreaterThan(0);
    }
    expect(labelOf("category", "IT Support", "en")).toBe("IT Support");
    expect(labelOf("category", "IT Support", "ar")).not.toBe("IT Support");
    expect(labelOf("priority", "high", "ar")).toBe(ar.priority.high);
  });
  it("returns unknown values unchanged", () => {
    expect(labelOf("category", "Parking", "ar")).toBe("Parking");
  });
});

describe("resolveLang", () => {
  it("cookie wins", () => expect(resolveLang("ar", "en-US")).toBe("ar"));
  it("falls back to Accept-Language with q-values", () => {
    expect(resolveLang(undefined, "fr;q=0.9, ar-JO;q=0.8, en;q=0.5")).toBe("ar");
    expect(resolveLang(undefined, "en-US,en;q=0.9,ar;q=0.8")).toBe("en");
  });
  it("defaults to en, ignoring a bad cookie", () => {
    expect(resolveLang("xx", null)).toBe("en");
    expect(resolveLang(undefined, "de,fr")).toBe("en");
  });
});
