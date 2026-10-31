#!/usr/bin/env python3
"""Deterministic cleaning pipeline for the AI Quest text-classification data.

Run:  python scripts/clean_data.py
Reads data/raw/{train,validation}.csv (utf-8-sig) and writes data/clean/*.
Labels (category, priority) are never modified.
NOTE: only train/validation are ever read; hidden test files are never touched.
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent.parent
RAW = BASE / "data" / "raw"
CLEAN = BASE / "data" / "clean"

# ---- known wrappers (from competition notes) -------------------------------
EN_PREFIXES = ["Could you assist?", "This is my issue:", "Hello,", "Hi team,", "Please help:",
               "Student request:", "University helpdesk:", "URGENT:", "I need assistance."]
EN_SUFFIXES = ["Please respond when possible."]
AR_PREFIXES = ["مرحبا يا جماعة", "مرحبا،", "لو سمحت", "عندي مشكلة:", "سؤال:", "ممكن تساعدوني؟", "ارجو المساعدة،"]
AR_SUFFIXES = ["وشكرا"]
KNOWN_PREFIXES = EN_PREFIXES + AR_PREFIXES
KNOWN_SUFFIXES = EN_SUFFIXES + AR_SUFFIXES

# ---- manually verified cross-lingual equivalents (Arabic core -> English core)
# Verified by reading the Arabic (Jordanian dialect). Scenarios not listed here
# (e.g. "الباص الاخير انلغى...", "صفحة التسجيل معلقة عندي", "البروجكتور بالغرفة مش شغال")
# have no English counterpart in train or val and are deliberately left unmapped.
AR_TO_EN = {
    "الضو بالممر خربان": "A hallway light is broken",
    "المبلغ الظاهر على حسابي مش صحيح": "The finance portal shows the wrong outstanding balance",
    "حسابي الجامعي تسكر وعندي امتحان اونلاين اليوم": "My university account is locked and I have an online exam today",
    "دفعت القسط ولسه مش ظاهر بالدفع والتسجيل بسكر اليوم": "My tuition payment is not reflected and registration closes today",
    "علامتي غلط وآخر يوم اعتراض اليوم": "My exam grade was recorded incorrectly and the appeal deadline is today",
    "عندي امتحانين بنفس الوقت": "The exam schedule has two tests at the same time",
    "في مي بتسرب جنب كهربا المختبر": "Water is leaking near an electrical socket in the lab",
    "كيف بغير كلمة السر؟": "How can I reset my university password?",
    "مش قادر اسجل مواد والنظام بعطيني خطأ": "I cannot add my courses because the registration portal rejects my request",
    "وين بلاقي مواعيد السحب والاضافة؟": "Where can I find the add-drop period dates?",
    "وين جدول الباصات؟": "Where can I see the shuttle bus timetable?",
    "باص الجامعة اتأخر عن موعده": "The university bus is running twenty minutes late",
}

AR_DIACRITICS = re.compile("[ً-ْٰـ]")  # harakat, dagger alif, tatweel
AR_CHARMAP = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"})
PUNCT = " \t\n.,;:!?؟،؛-"


def read_raw(name):
    return pd.read_csv(RAW / name, encoding="utf-8-sig", dtype=str, keep_default_na=False)


def detect_lang(t):
    ar = len(re.findall(r"[؀-ۿ]", t))
    lat = len(re.findall(r"[A-Za-z]", t))
    return "ar" if ar > lat else "en"


def collapse_ws(s):
    return re.sub(r"\s+", " ", s.replace(" ", " ")).strip()


def normalize(core, lang):
    s = collapse_ws(core)
    if lang == "en":
        s = s.lower()
    else:
        s = AR_DIACRITICS.sub("", s).translate(AR_CHARMAP)
    s = collapse_ws(s)
    return s.strip(PUNCT)


# ---- data-driven wrapper detection ------------------------------------------
def detect_wrappers(texts, max_tokens=5, min_support=3):
    """A prefix/suffix candidate (first/last 1..max_tokens tokens) is a wrapper if
    stripping it leaves a remainder that occurs as a bare row (exact full text) for
    at least `min_support` distinct remainders. Core-leading words like 'The' fail
    because the remainder ('exam schedule ...') is never a standalone row."""
    texts = [collapse_ws(t) for t in texts]
    bare = set(texts)
    pre, suf = defaultdict(set), defaultdict(set)
    for t in texts:
        tok = t.split(" ")
        for k in range(1, min(max_tokens, len(tok) - 1) + 1):
            p, r = " ".join(tok[:k]), " ".join(tok[k:])
            if r in bare:
                pre[p].add(r)
            s, r2 = " ".join(tok[-k:]), " ".join(tok[:-k])
            if r2 in bare:
                suf[s].add(r2)
    return ({p for p, v in pre.items() if len(v) >= min_support},
            {s for s, v in suf.items() if len(v) >= min_support})


def strip_wrappers(text, prefixes, suffixes):
    t = collapse_ws(text)
    pres, sufs = [], []
    pl = sorted(prefixes, key=len, reverse=True)
    sl = sorted(suffixes, key=len, reverse=True)
    changed = True
    while changed:
        changed = False
        for p in pl:
            if t.startswith(p) and len(t) > len(p):
                t = t[len(p):].strip(); pres.append(p); changed = True; break
        for s in sl:
            if t.endswith(s) and len(t) > len(s):
                t = t[:-len(s)].strip(); sufs.insert(0, s); changed = True; break
    return " ".join(pres), " ".join(sufs), t


def build(df, split, tag, prefixes, suffixes):
    rows = []
    for r in df.itertuples(index=False):
        pre, suf, core = strip_wrappers(r.text, prefixes, suffixes)
        lang = detect_lang(r.text)
        rows.append(dict(request_id=r.request_id, split=split, text=r.text, lang=lang, prefix=pre,
                         suffix=suf, core=core, text_norm=normalize(core, lang), category=r.category,
                         priority=r.priority, has_urgent_marker="URGENT" in r.text, n_chars=len(r.text)))
    out = pd.DataFrame(rows)
    ids, nxt = {}, 1
    for key in zip(out.lang, out.text_norm):
        if key not in ids:
            ids[key] = f"{tag}-S{nxt:02d}"; nxt += 1
    out["scenario_id"] = [ids[k] for k in zip(out.lang, out.text_norm)]
    cols = ["request_id", "split", "text", "lang", "prefix", "suffix", "core", "text_norm",
            "scenario_id", "category", "priority", "has_urgent_marker", "n_chars"]
    return out[cols]


def md_table(df, index=True):
    d = df.reset_index() if index else df
    head = "| " + " | ".join(map(str, d.columns)) + " |\n|" + "---|" * len(d.columns) + "\n"
    return head + "".join("| " + " | ".join(map(str, r)) + " |\n" for r in d.itertuples(index=False))


def run():
    CLEAN.mkdir(parents=True, exist_ok=True)
    raw_tr, raw_va = read_raw("train.csv"), read_raw("validation.csv")
    bom = {n: (RAW / n).read_bytes()[:3] == b"\xef\xbb\xbf" for n in ("train.csv", "validation.csv")}

    # data-driven detection (per split and pooled) and coverage assertions
    found = {}
    for nm, d in (("train", raw_tr), ("validation", raw_va), ("pooled", pd.concat([raw_tr, raw_va]))):
        found[nm] = detect_wrappers(d.text.tolist())
        extra_p = found[nm][0] - set(KNOWN_PREFIXES)
        extra_s = found[nm][1] - set(KNOWN_SUFFIXES)
        assert not extra_p and not extra_s, f"[{nm}] hardcoded list misses prefixes={extra_p} suffixes={extra_s}"
    prefixes = set(KNOWN_PREFIXES) | found["pooled"][0]
    suffixes = set(KNOWN_SUFFIXES) | found["pooled"][1]

    tr = build(raw_tr, "train", "TR", prefixes, suffixes)
    va = build(raw_va, "val", "VA", prefixes, suffixes)

    # scenarios
    comb = pd.concat([tr, va], ignore_index=True)
    sc = (comb.groupby("scenario_id", sort=False)
          .agg(split=("split", "first"), lang=("lang", "first"), core=("core", "first"),
               text_norm=("text_norm", "first"), n_cat=("category", "nunique"), n_pri=("priority", "nunique"),
               category=("category", "first"), priority=("priority", "first"),
               n_variants=("request_id", "size")).reset_index())
    assert (sc.n_cat == 1).all() and (sc.n_pri == 1).all(), "inconsistent labels inside a scenario"

    by_core = {r.core: r.scenario_id for r in sc.itertuples()}
    pairs, mism = [], []
    for ar, en in AR_TO_EN.items():
        assert ar in by_core and en in by_core, f"mapping not found in data: {ar} / {en}"
        a, e = by_core[ar], by_core[en]
        ra, re_ = sc.set_index("scenario_id").loc[a], sc.set_index("scenario_id").loc[e]
        ok = (ra.category, ra.priority) == (re_.category, re_.priority)
        pairs.append((a, ar, e, en, ra.split, re_.split, ra.category, ra.priority, re_.category, re_.priority, ok))
        if not ok:
            mism.append(pairs[-1])
    partner = {}
    for p in pairs:
        partner[p[0]] = p[2]; partner[p[2]] = p[0]
    sc["translation_of"] = sc.scenario_id.map(partner).fillna("")
    sc[["scenario_id", "split", "lang", "core", "category", "priority", "n_variants", "translation_of"]] \
        .to_csv(CLEAN / "scenarios.csv", index=False, encoding="utf-8")

    group = {s: min(s, partner.get(s, s)) for s in sc.scenario_id}
    comb["cv_group"] = comb.scenario_id.map(group)
    for d, n in ((tr, "train_clean.csv"), (va, "val_clean.csv")):
        d.to_csv(CLEAN / n, index=False, encoding="utf-8")
    comb.to_csv(CLEAN / "train_val_combined.csv", index=False, encoding="utf-8")

    # same-language cross-split exact overlap
    same_lang = set(zip(tr.lang, tr.text_norm)) & set(zip(va.lang, va.text_norm))

    # ---- sanity checks ----
    checks = []
    def chk(name, cond):
        assert cond, f"SANITY FAIL: {name}"; checks.append(name)
    chk("row counts preserved (train 370, val 62)", len(tr) == len(raw_tr) == 370 and len(va) == len(raw_va) == 62)
    chk("request_ids unique", comb.request_id.is_unique)
    chk("every row maps to a scenario", comb.scenario_id.notna().all() and (comb.scenario_id != "").all())
    chk("every scenario has a single category and a single priority", True)
    chk("no empty core / text_norm", (comb.core.str.len() > 0).all() and (comb.text_norm.str.len() > 0).all())
    chk("no residual prefix (core starts with no known/detected prefix)",
        not any(c.startswith(p) for c in comb.core for p in prefixes))
    chk("no residual suffix (core ends with no known/detected suffix)",
        not any(c.endswith(s) for c in comb.core for s in suffixes))
    chk("labels identical to raw",
        (tr[["request_id", "category", "priority"]].values == raw_tr[["request_id", "category", "priority"]].values).all()
        and (va[["request_id", "category", "priority"]].values == raw_va[["request_id", "category", "priority"]].values).all())
    chk("hardcoded wrapper lists cover all data-driven detections", True)
    chk("translated pairs have matching labels", not mism)
    chk("scenario counts 36 train / 6 val", sc[sc.split == "train"].shape[0] == 36 and sc[sc.split == "val"].shape[0] == 6)
    chk("cv_group never splits a translated pair", all(group[a] == group[b] for a, b in partner.items()))

    # ---- oddities ----
    glued = comb[(comb.suffix != "") & comb.apply(lambda r: r.text.rstrip().endswith(r.suffix) and
                 not re.search(r"[.,;:!?؟،]\s*" + re.escape(r.suffix) + r"$", r.text), axis=1)]
    ws_issue = int(comb.text.map(lambda t: t != collapse_ws(t)).sum())

    # ---- report ----
    L = []
    L.append("# Cleaning report\n")
    L.append(f"Inputs: data/raw/train.csv ({len(tr)} rows), data/raw/validation.csv ({len(va)} rows). "
             f"UTF-8 BOM present: {bom}. Read with utf-8-sig. Hidden test files were never accessed.\n")
    L.append("## Row and scenario counts\n")
    cnt = comb.groupby(["split", "lang"]).agg(rows=("request_id", "size"), scenarios=("scenario_id", "nunique"))
    L.append(md_table(cnt))
    L.append(f"\nTotals: train {len(tr)} rows / {tr.scenario_id.nunique()} scenarios; "
             f"val {len(va)} rows / {va.scenario_id.nunique()} scenarios.\n")
    L.append("## Label distributions (rows)\n")
    for split_name, d in (("train", tr), ("val", va), ("combined", comb)):
        L.append(f"### Category: {split_name}\n")
        L.append(md_table(d.category.value_counts().rename("rows").to_frame()))
        L.append(f"\n### Priority: {split_name}\n")
        L.append(md_table(d.priority.value_counts().rename("rows").to_frame()))
    for split_name, d in (("train", tr), ("val", va)):
        L.append(f"\n### Category x priority: {split_name}\n")
        L.append(md_table(pd.crosstab(d.category, d.priority)))
        L.append(f"\n### Language x priority: {split_name}\n")
        L.append(md_table(pd.crosstab(d.lang, d.priority)))
    L.append("\n### Scenario-level (unique scenarios) priority by language, combined\n")
    L.append(md_table(pd.crosstab(sc.lang, sc.priority)))
    L.append("\n## Prefixes and suffixes stripped\n")
    for nm, d in (("train", tr), ("val", va)):
        L.append(f"### Prefixes ({nm})\n")
        pc = d.prefix.replace("", "(none)").value_counts().rename("rows").to_frame()
        L.append(md_table(pc))
        L.append(f"\n### Suffixes ({nm})\n")
        sc_ = d.suffix.replace("", "(none)").value_counts().rename("rows").to_frame()
        L.append(md_table(sc_))
    L.append(f"\nData-driven detection (pooled): {len(found['pooled'][0])} prefixes, {len(found['pooled'][1])} suffixes; "
             f"all contained in the hardcoded lists (asserted). Hardcoded entries never seen in data: "
             f"{sorted((set(KNOWN_PREFIXES) - found['pooled'][0]) | (set(KNOWN_SUFFIXES) - found['pooled'][1])) or 'none'}.\n")
    L.append(f"URGENT marker rows: train {int(tr.has_urgent_marker.sum())}, val {int(va.has_urgent_marker.sum())}. "
             "Check: priority of URGENT rows vs others is determined by the scenario only (labels are consistent per scenario), "
             "so the marker carries no label signal.\n")
    L.append("## Sanity checks performed (all passed)\n")
    L += [f"- {c}\n" for c in checks]
    L.append("\n## Cross-lingual translation pairs (manually verified)\n")
    L.append("| Arabic scenario | Arabic core | English scenario | English core | splits (ar/en) | labels ar | labels en | match |\n|---|---|---|---|---|---|---|---|\n")
    for a, ar, e, en, sa, se, ca, pa, ce, pe, ok in pairs:
        flag = "LEAKAGE" if sa != se else "same split"
        L.append(f"| {a} | {ar} | {e} | {en} | {sa}/{se} ({flag}) | {ca}/{pa} | {ce}/{pe} | {'yes' if ok else 'NO'} |\n")
    leak = [p for p in pairs if p[4] != p[5]]
    L.append(f"\n{len(pairs)} pairs; {len(leak)} cross-split pairs (translation leakage between train and val). "
             f"Label mismatches: {len(mism)}. Same-language exact core overlap across splits: {sorted(same_lang) or 'none'}.\n")
    unm = sc[sc.translation_of == ""]
    L.append("\nScenarios with no translation counterpart: " + "; ".join(f"{r.scenario_id} ({r.core})" for r in unm.itertuples()) + "\n")
    L.append("\ncv_group in train_val_combined.csv = min(scenario_id, translation partner id) so a scenario and its translation share one group.\n")
    L.append("\n## Text oddities handled\n")
    L.append(f"- Rows whose suffix is glued to the core without punctuation: {len(glued)} (e.g. 'A hallway light is broken Please respond when possible.'); stripped by exact-suffix match.\n")
    L.append(f"- Rows with irregular whitespace (leading/trailing/double/NBSP) in raw text: {ws_issue}.\n")
    L.append("- UTF-8 BOM at file start handled via utf-8-sig.\n")
    L.append("- Arabic cores keep a trailing question mark in `core`; it is removed only in `text_norm`.\n")
    L.append("- English prefixes ending in '.'/'?' ('I need assistance.', 'Could you assist?') are stripped as whole strings, so no stray punctuation remains.\n")
    L.append("- `text` is kept raw and unchanged.\n")
    (CLEAN / "cleaning_report.md").write_text("".join(L), encoding="utf-8")
    return tr, va, comb, sc


if __name__ == "__main__":
    run()
    print((CLEAN / "cleaning_report.md").read_text(encoding="utf-8"))
