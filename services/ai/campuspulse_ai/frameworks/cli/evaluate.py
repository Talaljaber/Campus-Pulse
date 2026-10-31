"""`python services/ai/evaluate.py`: the offline evaluation entry point (ARCHITECTURE §1.2).

Today it has one mode, `--redteam` (P4.11, `frameworks/cli/redteam.py`). The report modes of P2.8
(`--all`, `--benchmark`, `--coverage`, ...; ML stream) are added here as further flags; until then any
other call exits 2 with a usage message.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from campuspulse_ai.composition.redteam import CoreFactory, load_offline_core
from campuspulse_ai.config.settings import Settings
from campuspulse_ai.frameworks.cli import redteam


def main(argv: Sequence[str] | None = None, *, core_factory: CoreFactory = load_offline_core) -> int:
    """Parse `argv` and run the chosen mode; returns the exit code."""
    settings = Settings()
    parser = argparse.ArgumentParser(prog="evaluate.py", description="CampusPulse offline evaluation.")
    parser.add_argument("--redteam", action="store_true", help="run the offline red team (P4.11)")
    redteam.add_arguments(parser, settings)
    args = parser.parse_args(argv)
    if args.redteam:
        return redteam.run(args, settings, core_factory)
    parser.error("choose a mode: --redteam (the report modes of P2.8 are not built yet)")


if __name__ == "__main__":
    raise SystemExit(main())
