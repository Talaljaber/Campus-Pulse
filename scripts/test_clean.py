#!/usr/bin/env python3
"""Plain-python tests: python scripts/test_clean.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pandas as pd
import clean_data as cd

tr, va, comb, sc = cd.run()
raw_tr, raw_va = cd.read_raw("train.csv"), cd.read_raw("validation.csv")
ctr = pd.read_csv(cd.CLEAN / "train_clean.csv", encoding="utf-8", dtype=str, keep_default_na=False)
cva = pd.read_csv(cd.CLEAN / "val_clean.csv", encoding="utf-8", dtype=str, keep_default_na=False)
cmb = pd.read_csv(cd.CLEAN / "train_val_combined.csv", encoding="utf-8", dtype=str, keep_default_na=False)

assert len(ctr) == len(raw_tr) == 370 and len(cva) == len(raw_va) == 62 and len(cmb) == 432
for c, r in ((ctr, raw_tr), (cva, raw_va)):
    assert list(c.request_id) == list(r.request_id)
    assert list(c.category) == list(r.category) and list(c.priority) == list(r.priority)
    assert list(c.text) == list(r.text)
assert not any(c.startswith(p) for c in cmb.core for p in cd.KNOWN_PREFIXES)
assert not any(c.endswith(s) for c in cmb.core for s in cd.KNOWN_SUFFIXES)
assert (cmb.core != "").all() and (cmb.text_norm != "").all()
assert ctr.scenario_id.nunique() == 36 and cva.scenario_id.nunique() == 6
assert len(pd.read_csv(cd.CLEAN / "scenarios.csv")) == 42
for _, g in cmb.groupby("scenario_id"):
    assert g.category.nunique() == 1 and g.priority.nunique() == 1
# translated pairs share a cv_group
s = pd.read_csv(cd.CLEAN / "scenarios.csv", keep_default_na=False)
grp = cmb.drop_duplicates("scenario_id").set_index("scenario_id").cv_group
for r in s[s.translation_of != ""].itertuples():
    assert grp[r.scenario_id] == grp[r.translation_of]
assert cmb.cv_group.nunique() == 42 - len(cd.AR_TO_EN)
# normalisation examples
assert cd.normalize("كيف بغير كلمة السر؟", "ar") == "كيف بغير كلمه السر"
assert cd.normalize("Where can I meet my academic advisor?", "en") == "where can i meet my academic advisor"
print("ALL TESTS PASSED")
