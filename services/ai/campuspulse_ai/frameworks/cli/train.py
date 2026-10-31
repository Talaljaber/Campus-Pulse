"""`train.py`: stage A (OOF) → provisional stage B → stage C (freeze) (P1.16, ARCHITECTURE §3.4).

    python services/ai/train.py [--out models/frozen/v1] [--report reports/cv_p1.json] [--cv-only] [--fast]
                                [--encoder {onnx,hashing}] [--retune] [--data CSV ...] [--folds CSV]

The last line is `froze v1: members=... cat_macroF1_oof_official=x.xxx pri_macroF1_oof_official=x.xxx
sha=<12 hex>` (or `cv only: ...` with `--cv-only`). Exit codes: 0 ok; 2 the encoder is missing or does not
match `config/train.yaml` (the message has the export/fetch command); 4 invalid input (e.g. a holdout path).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from campuspulse_ai.composition.training import TrainOptions, run_training
from campuspulse_ai.domain.errors import ArtifactError, InvalidInput

EXIT_OK, EXIT_ARTIFACT, EXIT_INPUT = 0, 2, 4
EXPORT_HINT = (
    "export it with `python -m campuspulse_ai.frameworks.cli.export_encoder --model "
    "intfloat/multilingual-e5-small --revision <config/train.yaml encoder.revision> --out <out>/encoder` "
    "or fetch it with `python scripts/fetch_models.py`"
)


def _parser() -> argparse.ArgumentParser:
    d = TrainOptions()
    p = argparse.ArgumentParser(prog="train.py", description=__doc__.split("\n\n")[0])
    p.add_argument("--out", type=Path, default=d.out, help="frozen model dir to write (default %(default)s)")
    p.add_argument("--report", type=Path, default=d.report, help="CV report path (default %(default)s)")
    p.add_argument("--cv-only", action="store_true", help="stages A and B only; write the report, no freeze")
    p.add_argument("--fast", action="store_true", help="skip the stage-B grids (no grid runs in P1)")
    p.add_argument(
        "--encoder",
        choices=("onnx", "hashing"),
        default=d.encoder,
        help="onnx = the frozen int8 encoder in <out>/encoder; hashing = test fixtures only",
    )
    p.add_argument("--retune", action="store_true", help="re-read config/hand_tuned.yaml (always done in P1)")
    p.add_argument(
        "--data",
        type=Path,
        nargs="+",
        default=None,
        help="training CSVs (default: data/clean/train_val_combined.csv + data/augmented/*.csv)",
    )
    p.add_argument("--folds", type=Path, default=d.folds_csv, help="frozen cv_group,cv_fold table")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    opts = TrainOptions(
        out=args.out,
        report=args.report,
        cv_only=args.cv_only,
        fast=args.fast,
        retune=args.retune,
        encoder=args.encoder,
        data=tuple(args.data or ()),
        folds_csv=args.folds,
    )
    try:
        outcome = run_training(opts)
    except InvalidInput as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INPUT
    except ArtifactError as exc:
        print(f"error: {exc}\n{EXPORT_HINT}", file=sys.stderr)
        return EXIT_ARTIFACT
    print(outcome.summary)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
