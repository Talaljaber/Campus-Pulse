"""D-057: predict.py uses the LLM front end by default when a key exists, offline otherwise."""

from __future__ import annotations

import argparse

import pytest
from pydantic import SecretStr

from campuspulse_ai.config.settings import Settings
from campuspulse_ai.frameworks.cli.predict import llm_mode


def _args(*, offline: bool = False, use_llm: bool = False) -> argparse.Namespace:
    return argparse.Namespace(offline=offline, use_llm=use_llm)


def _settings(key: str | None) -> Settings:
    return Settings(_env_file=None, openrouter_api_key=SecretStr(key) if key else None)


@pytest.mark.parametrize(
    ("offline", "use_llm", "key", "expected"),
    [
        (False, False, "sk-test", True),  # default with a key: LLM on
        (False, False, None, False),  # default without a key: offline
        (True, False, "sk-test", False),  # --offline always wins
        (False, True, None, True),  # --use-llm asks for it (build_offline exits 3 without a key)
        (False, True, "sk-test", True),
    ],
)
def test_llm_mode(offline: bool, use_llm: bool, key: str | None, expected: bool) -> None:
    assert llm_mode(_args(offline=offline, use_llm=use_llm), _settings(key)) is expected
