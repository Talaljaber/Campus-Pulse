"""P7.12: implicit account compromise (no "hacked", no "urgent") floors priority to high."""

from __future__ import annotations

import csv

import pytest
import yaml

from campuspulse_ai.adapters.models.urgency_floor import UrgencyFloorRule
from campuspulse_ai.adapters.preprocess.normalizer import DefaultNormalizer
from campuspulse_ai.config.paths import CONFIG_DIR, DATA_CLEAN, LEXICONS

MAX_TOKENS = yaml.safe_load((CONFIG_DIR / "train.yaml").read_text(encoding="utf-8"))["guards"]["max_tokens"]

POSITIVE = [
    "my password was changed and I did not do it",
    "I got a login alert from another country on my student account",
    "someone is logged in to my account right now",
    "emails I never sent went out from my university email",
    "I cannot log in and my recovery email was changed",
    "كلمة السر تغيرت وأنا ما غيرتها حسابي في البوابة",
    "وصلني تنبيه تسجيل دخول من دولة أخرى على حسابي",
    "حدا داخل على حسابي بالبوابة",
    "ايميلات ما بعتها طلعت من ايميلي",
    "el password etghayyar w mesh ana illi ghayyarto 3ala el account",
    "jani alert login men jehaz ghareeb 3ala el hesab",
]

NEGATIVE = [
    "I forgot my password",
    "please reset my password",
    "I cannot log in to the portal",
    "I did not receive the confirmation email about my account",
    "how do I change my password in the student portal",
    "nsit el password w badi a3mel reset",
    "ما بقدر ادخل على البوابة",
    "my new device cannot connect to the campus wifi",
]


@pytest.fixture(scope="module")
def rule() -> UrgencyFloorRule:
    return UrgencyFloorRule.from_yaml(LEXICONS / "urgency.yaml")


@pytest.fixture(scope="module")
def normalizer() -> DefaultNormalizer:
    return DefaultNormalizer.from_lexicons(LEXICONS, MAX_TOKENS)


@pytest.mark.parametrize("text", POSITIVE)
def test_implicit_compromise_fires(rule: UrgencyFloorRule, normalizer: DefaultNormalizer, text: str) -> None:
    assert "account_compromise" in rule.hits(normalizer.normalize(text)), text


@pytest.mark.parametrize("text", NEGATIVE)
def test_ordinary_account_requests_do_not_fire(
    rule: UrgencyFloorRule, normalizer: DefaultNormalizer, text: str
) -> None:
    assert rule.hits(normalizer.normalize(text)) == (), text


def test_official_hits_are_all_gold_high(rule: UrgencyFloorRule, normalizer: DefaultNormalizer) -> None:
    with (DATA_CLEAN / "train_val_combined.csv").open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    bad = [
        r["request_id"]
        for r in rows
        if r["priority"] != "high" and "account_compromise" in rule.hits(normalizer.normalize(r["text"]))
    ]
    assert bad == []
