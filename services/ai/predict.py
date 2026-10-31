"""Entry point: `python services/ai/predict.py --input <csv> --output <csv>` (see frameworks.cli.predict)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # run from a checkout without `pip install -e`

from campuspulse_ai.frameworks.cli.predict import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
