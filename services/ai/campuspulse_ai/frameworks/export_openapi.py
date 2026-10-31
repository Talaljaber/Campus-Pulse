"""Export the OpenAPI document of the `/v1` contract.

Usage (from the repo root, inside the venv):
    python -m campuspulse_ai.frameworks.export_openapi --out services/ai/openapi.json         # real app
    python -m campuspulse_ai.frameworks.export_openapi --mock --out services/ai/openapi.json  # mock app

Both apps declare the same routes (`api_contract.route_kwargs`), so both exports are byte-identical
(`tests/contracts/test_openapi_real_app.py`). The output is deterministic, ASCII-only JSON (indent 2,
LF line endings, trailing newline), so CI can diff it. `--out` avoids PowerShell 5.1's `>` re-encoding.

Exit codes: 0 written; 2 the requested app could not be imported.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def openapi_document(*, mock: bool) -> dict[str, Any]:
    """The OpenAPI dict of the mock app (`mock=True`) or the real app. Raises RuntimeError if absent."""
    if mock:
        from campuspulse_ai.frameworks.mock_app import create_mock_app

        return create_mock_app().openapi()
    try:
        from campuspulse_ai.frameworks.fastapi_app import create_app
    except ImportError as exc:
        raise RuntimeError("the real app (frameworks/fastapi_app.py) does not exist yet; use --mock") from exc
    document: dict[str, Any] = create_app().openapi()
    return document


def render(document: dict[str, Any]) -> str:
    """Serialize deterministically: ASCII-only, indent 2, trailing newline."""
    return json.dumps(document, indent=2, ensure_ascii=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; see the module docstring."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--mock", action="store_true", help="export the fixture-backed mock app (P0.13)")
    parser.add_argument("--out", type=Path, help="write to this file instead of stdout")
    args = parser.parse_args(argv)
    try:
        text = render(openapi_document(mock=args.mock))
    except RuntimeError as exc:
        print(f"export_openapi: {exc}", file=sys.stderr)
        return 2
    data = text.encode("ascii")
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(data)
    else:
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
