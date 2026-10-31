# data/robustness/: robustness probes

**Never trained on.** This folder is never read by `train.py`; only `evaluate.py` reads this folder (ARCHITECTURE §3.2).
`train.py` and `load_pool` refuse any input path that contains `robustness` (`campuspulse_ai.config.paths.is_holdout`).

- `probes.csv` (task P2.5): perturbed versions of our own test rows, tagged by style
  (wrappers, typos, Arabizi, injection, `deadline_shortcut`, ...). Agents draft them; the developer verifies them.
