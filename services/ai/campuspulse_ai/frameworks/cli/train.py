"""`train.py`: stage A (OOF) → stage B (tuned on OOF) → stage C (freeze) (P1.16, P2.7, ARCHITECTURE §3.4).

    python services/ai/train.py [--out models/frozen/v1] [--report reports/cv_p2.json] [--cv-only] [--fast]
                                [--encoder {onnx,hashing}] [--encoder-dir DIR] [--retune] [--data CSV ...]
                                [--folds CSV]

The last line is `froze v1: members=... weights_cat={...} cat_macroF1_oof_official=x.xxx
pri_macroF1_oof_official=x.xxx nested_cat=x.xxx nested_pri=x.xxx q_cat=x.xx q_pri=x.xx sha=<12 hex>` (or
`cv only: ...` with `--cv-only`, `retuned v1: ...` with `--retune`). Exit codes: 0 ok; 2 the encoder is
missing or does not match `config/train.yaml` (the message has the export/fetch command); 4 invalid input
(e.g. a holdout path).
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
    p.add_argument("--fast", action="store_true",
                   help="skip the C grids (grid midpoints) and the nested estimates (tests, quick looks)")
    p.add_argument(
        "--encoder",
        choices=("onnx", "hashing"),
        default=d.encoder,
        help="onnx = the frozen int8 encoder in <out>/encoder; hashing = test fixtures only",
    )
    p.add_argument("--retune", action="store_true",
                   help="recompute conformal quantiles and human_review_maxprob of --out from its oof.npz")
    p.add_argument("--encoder-dir", type=Path, default=None,
                   help="another exported encoder for a --cv-only comparison (P2.6)")
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
        encoder_dir=args.encoder_dir,
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
