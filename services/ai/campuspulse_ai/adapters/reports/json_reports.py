"""JsonReportsSource: the model-lab report file for `/v1/metrics` (P4.12; `ReportsSource`).

`REPORTS_DIR/model_lab.json` is written by `evaluate.py` (ML stream) and copied into the image. Its
shape is the offline part of `dto.MetricsResponse`:

```json
{"generated_at": "2026-11-04T22:10:00+03:00", "ask_rate": 0.18, "ask_rate_is_proxy": true,
 "benchmark": [...], "coverage": [...], "calibration": [...], "fairness": [...],
 "ablations": [...], "confusions": [...]}
```
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from campuspulse_ai.domain.errors import InvalidInput

REPORT_FILE = "model_lab.json"


class JsonReportsSource:
    """`load()`: the parsed report, or None when the file does not exist (no evaluation yet).

    Raises `InvalidInput` when the file is not UTF-8 JSON or not a JSON object. Read on every call (the
    file is small and the page is rarely opened), so a new report shows up without a restart.
    """

    def __init__(self, reports_dir: Path, file_name: str = REPORT_FILE) -> None:
        self._path = reports_dir / file_name

    def load(self) -> Mapping[str, object] | None:
        try:
            text = self._path.read_text(encoding="utf-8-sig")
        except FileNotFoundError:
            return None
        except (OSError, UnicodeDecodeError) as exc:
            raise InvalidInput(f"{self._path.name} cannot be read: {exc}") from exc
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise InvalidInput(f"{self._path.name} is not JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise InvalidInput(f"{self._path.name} is not a JSON object")
        return data
