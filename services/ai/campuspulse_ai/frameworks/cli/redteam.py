"""Offline red-team CLI (P4.11): `python services/ai/evaluate.py --redteam [options]`.

Runs `composition.redteam.run_offline_redteam`: the frozen offline core (memory off), an in-memory
repository, the rule-based generator over the official training rows (or `--seed-csv`), and writes
`reports/redteam/<stamp>.json` plus `reports/redteam/candidates_<stamp>.csv` for the failures.
No network, no LLM, no database.

Options: `--n` (default and maximum `REDTEAM_MAX_N`, 200), `--seed` (42), `--styles a,b` (default all),
`--seed-csv` (default `REDTEAM_SEED_CSV`; holdouts are refused), `--model-dir` (default
`ARTIFACT_DIR`), `--out-dir` (default `reports/redteam`).

Prints `scorecard overall=0.xx n=N run=<id> written reports/redteam/<stamp>.json` and one line with
the robustness properties. Exit codes: 0 done; 2 no usable model (`ArtifactError`); 4 bad input
(`InvalidInput`: n, a style, the seed file); 5 a bad `config/redteam.yaml` or lexicon.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from campuspulse_ai.composition.redteam import (
    REDTEAM_REPORTS,
    CoreFactory,
    OfflineRedTeam,
    load_offline_core,
    run_offline_redteam,
)
from campuspulse_ai.config.paths import REPO_ROOT
from campuspulse_ai.config.settings import Settings
from campuspulse_ai.domain.errors import ArtifactError, InvalidInput

DEFAULT_SEED = 42
EXIT_OK = 0
EXIT_ARTIFACT = 2
EXIT_INPUT = 4
EXIT_CONFIG = 5


def add_arguments(parser: argparse.ArgumentParser, settings: Settings) -> None:
    """The red-team options (shared with `evaluate.py`)."""
    parser.add_argument("--n", type=int, default=settings.redteam_max_n, help="items (max REDTEAM_MAX_N)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="generator seed")
    parser.add_argument("--styles", default="", help="comma-separated styles (default: all)")
    parser.add_argument("--seed-csv", type=Path, default=None, help="seed rows (default REDTEAM_SEED_CSV)")
    parser.add_argument("--model-dir", type=Path, default=None, help="model dir (default ARTIFACT_DIR)")
    parser.add_argument("--out-dir", type=Path, default=REDTEAM_REPORTS, help="where reports are written")


def run(args: argparse.Namespace, settings: Settings, core_factory: CoreFactory = load_offline_core) -> int:
    """Run with parsed arguments; returns the exit code (module docstring)."""
    styles = [s.strip() for s in str(args.styles).split(",") if s.strip()]
    try:
        result = run_offline_redteam(
            n=args.n,
            styles=styles,
            seed=args.seed,
            settings=settings,
            model_dir=args.model_dir,
            seed_csv=args.seed_csv,
            out_dir=args.out_dir,
            core_factory=core_factory,
        )
    except ArtifactError as exc:
        print(f"error: no usable model: {exc}", file=sys.stderr)
        return EXIT_ARTIFACT
    except InvalidInput as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INPUT
    except (KeyError, ValueError) as exc:
        print(f"error: bad red-team config: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    _print(result)
    return EXIT_OK


def main(argv: Sequence[str] | None = None, *, core_factory: CoreFactory = load_offline_core) -> int:
    """`python -m campuspulse_ai.frameworks.cli.redteam [options]` (module docstring)."""
    settings = Settings()
    parser = argparse.ArgumentParser(description="Run the offline red team (P4.11).")
    add_arguments(parser, settings)
    return run(parser.parse_args(argv), settings, core_factory)


def _print(result: OfflineRedTeam) -> None:
    print(
        f"scorecard overall={result.overall:.2f} n={result.n} run={result.run_id} "
        f"written {_shown(result.report)}"
    )
    print(f"properties {_properties(result.properties)}")
    if result.candidates is not None:
        print(f"failure candidates (needs_human_check) written {_shown(result.candidates)}")


def _properties(props: Mapping[str, float | None]) -> str:
    return " ".join(f"{k}={'n/a' if v is None else f'{v:.2f}'}" for k, v in props.items())


def _shown(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
