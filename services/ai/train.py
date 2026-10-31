"""Entry point: `python services/ai/train.py ...` (see `campuspulse_ai.frameworks.cli.train`)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # run from a checkout without `pip install -e`

from campuspulse_ai.frameworks.cli.train import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
