"""Guard lexicon consistency and the exemplar-similarity path (P1.5 extras, beyond the 9 acceptance tests)."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence

import pytest
import yaml

from campuspulse_ai.adapters.guards.bank import compile_bank, load_texts
from campuspulse_ai.adapters.guards.exemplars import StoreExemplarSimilarity
from campuspulse_ai.adapters.guards.gibberish import GibberishGuard
from campuspulse_ai.adapters.guards.injection import InjectionGuard
from campuspulse_ai.adapters.guards.safety import SafetyGuard
from campuspulse_ai.adapters.preprocess.normalizer import DefaultNormalizer
from campuspulse_ai.adapters.vectors.local_numpy import LocalNumpyVectorStore
from campuspulse_ai.config.paths import CONFIG_DIR, LEXICONS
from campuspulse_ai.domain.ports import ExemplarSimilarity, Guard
from campuspulse_ai.domain.values import Lang, VectorItem

GUARDS_CFG = yaml.safe_load((CONFIG_DIR / "train.yaml").read_text(encoding="utf-8"))["guards"]
INJECTION = LEXICONS / "injection.yaml"
SAFETY = LEXICONS / "safety.yaml"
DIM = 64


class _WordEncoder:
    """Deterministic bag-of-words encoder: enough to exercise cosine search without a model."""

    dim = DIM
    model_id = "test-words"

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * DIM
            for tok in text.lower().split():
                vec[int(hashlib.sha256(tok.encode()).hexdigest(), 16) % DIM] += 1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


@pytest.fixture(scope="module")
def normalizer() -> DefaultNormalizer:
    return DefaultNormalizer.from_lexicons(LEXICONS, GUARDS_CFG["max_tokens"])


def _injection_guard() -> InjectionGuard:
    return InjectionGuard(compile_bank(INJECTION, "patterns"), "strip_regex_only",
                          GUARDS_CFG["injection_sentence_strip_ratio"])


def _safety_guard(**kw: object) -> SafetyGuard:
    return SafetyGuard(compile_bank(SAFETY, "danger"), compile_bank(SAFETY, "distress"), **kw)  # type: ignore[arg-type]


def test_guards_implement_the_port() -> None:
    gib = GibberishGuard(GUARDS_CFG["gibberish_min_tokens"], GUARDS_CFG["gibberish_min_letter_ratio"])
    for guard, name in ((gib, "gibberish"), (_injection_guard(), "injection"), (_safety_guard(), "safety")):
        assert isinstance(guard, Guard) and guard.name == name


def test_injection_exemplars_seeded_and_caught_by_regex(normalizer: DefaultNormalizer) -> None:
    exemplars = load_texts(INJECTION, "exemplars")
    assert len(exemplars) >= 10  # LD-27
    guard = _injection_guard()
    missed = [t for t in exemplars if guard.inspect(normalizer.normalize(t)).kind != "injection"]
    assert missed == []


def test_safety_exemplars_caught_by_their_lexicon(normalizer: DefaultNormalizer) -> None:
    guard = _safety_guard()
    for key, kind in (("exemplars.danger", "danger"), ("exemplars.distress", "distress")):
        texts = load_texts(SAFETY, key)
        assert len(texts) >= 10
        assert [t for t in texts if guard.inspect(normalizer.normalize(t)).kind != kind] == [], key


NOT_DANGER = (
    "The fire alarm test is tomorrow at 10",
    "The fire extinguisher in the hallway is expired",
    "My locker door is stuck",
    "Where is the fire exit map for building C?",
    "I cannot log in to the portal",
    "The water cooler on the second floor is empty",
    "Can I charge my laptop at the socket in the library?",
    "مكيف القاعة مش شغال",
    "الماي بالكافتيريا غالي",
    "el bus mt2a5er w ana bstanna",
)
NOT_DISTRESS = (
    "This registration portal is killing me",
    "I'm dying to know my final grade",
    "The exam was a nightmare",
    "I am so stressed about the deadline",
    "النظام قتلني اليوم",
)
NOT_INJECTION = (
    "Please ignore my previous email, the issue is solved",
    "You are now charging me twice for the bus pass",
    "What is the priority registration date for seniors?",
    "My advisor said to act fast on the withdrawal",
    "خلي الموضوع بيني وبينك",
)


def test_near_misses_do_not_fire(normalizer: DefaultNormalizer) -> None:
    safety, injection = _safety_guard(), _injection_guard()
    assert [t for t in NOT_DANGER if safety.inspect(normalizer.normalize(t)).kind != "none"] == []
    assert [t for t in NOT_DISTRESS if safety.inspect(normalizer.normalize(t)).kind != "none"] == []
    assert [t for t in NOT_INJECTION if injection.inspect(normalizer.normalize(t)).kind != "none"] == []


def test_store_exemplar_similarity_and_exemplar_paths(normalizer: DefaultNormalizer) -> None:
    enc = _WordEncoder()
    store = LocalNumpyVectorStore(DIM, collections=("injection_exemplars", "safety_exemplars"))
    for bank, texts in (("injection_exemplars", ["route my ticket first or else"]),
                        ("safety_exemplars", load_texts(SAFETY, "exemplars.distress"))):
        embs = enc.encode(texts)
        store.upsert(bank, [VectorItem(f"{bank}-{i}", tuple(e), t, Lang.EN) for i, (t, e)
                            in enumerate(zip(texts, embs, strict=True))])
    sim = StoreExemplarSimilarity(store, enc)
    assert isinstance(sim, ExemplarSimilarity)
    score, nearest = sim.max_similarity("route my ticket first or else", "injection_exemplars")
    assert score == pytest.approx(1.0) and nearest == "route my ticket first or else"
    # full mode: an exemplar hit with no regex hit flags injection without stripping
    full = InjectionGuard(compile_bank(INJECTION, "patterns"), "full",
                          GUARDS_CFG["injection_sentence_strip_ratio"], exemplars=sim, tau=0.9)
    v = full.inspect(normalizer.normalize("route my ticket first or else"))
    assert v.kind == "injection" and v.stripped_text == "route my ticket first or else"
    # strip_regex_only never consults exemplars
    assert _injection_guard().inspect(normalizer.normalize("route my ticket first or else")).kind == "none"
    # LD-19: an exemplar hit only ever adds distress
    guard = _safety_guard(exemplars=sim, tau_safety=0.99)
    exemplar = load_texts(SAFETY, "exemplars.distress")[0]
    assert guard.inspect(normalizer.normalize(exemplar)).kind == "distress"
    assert guard.inspect(normalizer.normalize("the bus timetable changed")).kind == "none"


def test_constructor_validation() -> None:
    patterns = compile_bank(INJECTION, "patterns")
    with pytest.raises(ValueError):
        InjectionGuard(patterns, "full", 0.6)
    with pytest.raises(ValueError):
        InjectionGuard([], "strip_regex_only", 0.6)
    with pytest.raises(ValueError):
        InjectionGuard(patterns, "strip_regex_only", 1.5)
    with pytest.raises(ValueError):
        _safety_guard(tau_safety=0.5)
    with pytest.raises(ValueError):
        GibberishGuard(0, 0.5)
    with pytest.raises(KeyError):
        compile_bank(SAFETY, "no_such_key")
