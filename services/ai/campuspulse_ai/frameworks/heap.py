"""Give freed heap memory back to the OS after startup (P4.13, ARCHITECTURE §3.17).

Loading the model allocates and frees large temporary buffers (the ONNX protobuf, the tokenizer JSON);
glibc keeps the freed pages in the process, so RSS stays about 15 MB above what the service uses.
`malloc_trim(0)` returns them. It exists only in glibc (the Linux image); on Windows, macOS or musl it
is skipped. Never raises.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import gc
import logging
import sys

log = logging.getLogger(__name__)

GLIBC = "c"
LINUX = "linux"


def trim_heap() -> bool:
    """Collect garbage (startup leaves reference cycles behind), then call glibc `malloc_trim(0)`.
    Returns True when the trim ran (and released memory), else False."""
    gc.collect()
    if not sys.platform.startswith(LINUX):
        return False
    name = ctypes.util.find_library(GLIBC)
    if not name:
        return False
    try:
        trim = ctypes.CDLL(name).malloc_trim
    except (OSError, AttributeError):  # not glibc (e.g. musl has no malloc_trim)
        return False
    try:
        released = bool(trim(0))
    except Exception as exc:  # a foreign call must never stop the startup
        log.warning("malloc_trim failed: %s", exc)
        return False
    log.info("malloc_trim(0) after startup: memory released=%s", released)
    return released
