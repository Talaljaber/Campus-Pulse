"""`python services/ai/evaluate.py`: the offline evaluation entry point (ARCHITECTURE §1.2).

    python services/ai/evaluate.py --redteam --n 200 --seed 42 [...]                  # P4.11 (Backend)
    python services/ai/evaluate.py [--all] [--benchmark] [--coverage] [--fairness] [--ablations]
                                   [--robustness] [--errors] [--eda] [--use-llm]
                                   [--model-dir models/frozen] [--reports reports]     # P2.8/P2.9 (ML)

The report modes (`composition/evaluation.py`) score the frozen model on OOF (its `oof.npz`), our own test
set (pooled and per set) and the probes, and write `reports/{metrics.json, benchmark.md, coverage.json,
fairness.json, ablations.json, errors.json, eda.json, confusions/}` plus `model_lab.json`. The last line is
`wrote reports/{...} (artifact v1 sha=<12 hex>)`. Exit codes: 0 ok; 2 an artifact problem. `--use-llm` keeps
the LLM rows `n/a` offline (the tier lives in the API, P3). No network otherwise.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from campuspulse_ai.composition.redteam import CoreFactory, load_offline_core
from campuspulse_ai.config.paths import MODELS_FROZEN, REPORTS
from campuspulse_ai.config.settings import Settings
from campuspulse_ai.domain.errors import ArtifactError
from campuspulse_ai.frameworks.cli import redteam

EXIT_OK, EXIT_ARTIFACT = 0, 2
REPORT_MODES = ("all", "benchmark", "coverage", "fairness", "ablations", "robustness", "errors", "eda")


def main(argv: Sequence[str] | None = None, *, core_factory: CoreFactory = load_offline_core) -> int:
    """Parse `argv` and run the chosen mode; returns the exit code."""
    settings = Settings()
    parser = argparse.ArgumentParser(prog="evaluate.py", description="CampusPulse offline evaluation.")
    parser.add_argument("--redteam", action="store_true", help="run the offline red team (P4.11)")
    for mode in REPORT_MODES:
        parser.add_argument(f"--{mode}", action="store_true", help=f"write the {mode} report(s) (P2.8/P2.9)")
    parser.add_argument(
        "--use-llm", action="store_true", help="LLM rows stay n/a offline (P3 wires the tier)"
    )
    parser.add_argument(
        "--reports", type=Path, default=REPORTS, help="report directory (default %(default)s)"
    )
    redteam.add_arguments(parser, settings)  # adds --model-dir (default models/frozen) among others
    args = parser.parse_args(argv)
    if args.redteam:
        return redteam.run(args, settings, core_factory)
    modes = frozenset(m for m in REPORT_MODES if getattr(args, m))
    if not modes:
        parser.error(
            "choose a mode: --all, --benchmark, --coverage, --fairness, --ablations, --robustness, "
            "--errors, --eda or --redteam"
        )
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    from campuspulse_ai.composition.evaluation import EvalOptions, load_eval_cfg, run_evaluation

    opts = EvalOptions(
        model_dir=args.model_dir or MODELS_FROZEN,
        reports=args.reports,
        eval_cfg=load_eval_cfg(),
        modes=modes,
        use_llm=args.use_llm,
    )
    try:
        print(run_evaluation(opts, settings=settings))
    except ArtifactError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ARTIFACT
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
