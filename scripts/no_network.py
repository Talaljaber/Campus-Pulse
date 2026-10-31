"""Run a Python script with the network disabled (P1.17): a tripwire that proves `predict.py` is offline.

    python scripts/no_network.py services/ai/predict.py --input data/raw/validation.csv --output .tmp/pred.csv

Before the script starts, every way to open a connection or resolve a name raises `OSError("network
disabled by scripts/no_network.py")`: `socket.socket.connect`/`connect_ex`, `socket.create_connection`,
`socket.getaddrinfo` and `socket.gethostbyname(_ex)`. Local socketpairs used by asyncio and ONNX Runtime
threads still work. The script runs as `__main__` with its own argv; its exit code is passed through.
Stdlib only.
"""

from __future__ import annotations

import runpy
import socket
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import NoReturn

MESSAGE = "network disabled by scripts/no_network.py"


def _blocked(*_args: object, **_kwargs: object) -> NoReturn:
    raise OSError(MESSAGE)


def disable_network() -> None:
    """Patch the socket module so no connection or DNS lookup can happen in this process."""
    patches: dict[str, Callable[..., NoReturn]] = {
        "create_connection": _blocked,
        "getaddrinfo": _blocked,
        "gethostbyname": _blocked,
        "gethostbyname_ex": _blocked,
    }
    for name, fn in patches.items():
        setattr(socket, name, fn)
    socket.socket.connect = _blocked  # type: ignore[method-assign]
    socket.socket.connect_ex = _blocked  # type: ignore[method-assign]


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: python scripts/no_network.py <script.py> [args...]", file=sys.stderr)
        return 2
    script = Path(args[0])
    if not script.is_file():
        print(f"error: {script} not found", file=sys.stderr)
        return 2
    disable_network()
    sys.argv = [str(script), *args[1:]]
    try:
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit as exc:
        code = exc.code
        return code if isinstance(code, int) else (0 if code is None else 1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
