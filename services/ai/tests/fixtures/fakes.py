"""Test fakes shared across streams (ARCHITECTURE §1.5).

`HashingEncoder` (P1.6) now lives in the package (`adapters/models/hashing_encoder.py`) because
`train.py --encoder hashing` builds the `tiny_model_dir` fixture with it; it is re-exported here.
"""

from __future__ import annotations

from campuspulse_ai.adapters.models.hashing_encoder import HashingEncoder

__all__ = ["HashingEncoder"]
