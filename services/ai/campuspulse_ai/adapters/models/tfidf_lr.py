"""M1 `TfidfLR`: TF-IDF (char_wb + word n-grams) → LogisticRegression (P1.10, SPEC §5.1[5], §3.6).

The transparent member. It sees `model_text` (normalized core, or `translit | original` for Arabizi), so it
is robust to typos (char n-grams) and gives token contributions for the explainer (P3).

Two choices make `sample_weight` exactly equivalent to duplicating rows (soft targets are weighted
duplicates, §3.3):
  - the vectorizer is fitted on the **distinct** texts, so wrapper variants and soft-target copies of one text
    do not change the IDF;
  - class balancing uses `probs.balanced_sample_weight` (weighted counts) instead of sklearn's row-count
    `class_weight="balanced"`.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore[import-untyped, unused-ignore]
from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped, unused-ignore]
from sklearn.pipeline import FeatureUnion  # type: ignore[import-untyped, unused-ignore]

from campuspulse_ai.adapters.models.probs import (
    LR_MAX_ITER,
    Target,
    balanced_sample_weight,
    check_labels,
    load_estimator,
    reorder,
    save_estimator,
    target_labels,
    to_vectors,
)
from campuspulse_ai.domain.values import ProbVector

KIND = "tfidf_lr"
CHAR = "char"
WORD = "word"
_WS = re.compile(r"\s+")


class TfidfLR:
    """Implements `domain.ports.ProbabilisticClassifier` (`name = "m1"`) for one target.

    `fit(texts, y, sample_weight)`: `FeatureUnion(char_wb char_ngram, word word_ngram)` TF-IDF fitted on the
    distinct texts, then `LogisticRegression(C, lbfgs, max_iter=2000)` with balanced weights (module
    docstring). `predict_proba(texts)` returns one `ProbVector` per text in the target's label order.
    `token_contributions(text)` explains the argmax class (see its docstring).

    Raises:
        ValueError: `fit` with an unknown label or mismatched lengths; `predict_proba` before `fit`.
        ArtifactMissing / ArtifactVersionMismatch: from `load`.
    """

    name = "m1"

    def __init__(
        self,
        target: Target,
        char_ngram: tuple[int, int],
        word_ngram: tuple[int, int],
        C: float,
        seed: int,
    ) -> None:
        """
        Args:
            target: `category` or `priority`.
            char_ngram, word_ngram, C: `FrozenConfig.m1.*`.
            seed: `FrozenConfig.seed` (the LR random state; lbfgs is deterministic anyway).
        """
        self.target: Target = target
        self.labels = target_labels(target)
        self.char_ngram = (int(char_ngram[0]), int(char_ngram[1]))
        self.word_ngram = (int(word_ngram[0]), int(word_ngram[1]))
        self.C = float(C)
        self.seed = int(seed)
        self._features: FeatureUnion | None = None
        self._lr: LogisticRegression | None = None

    def _new_features(self) -> FeatureUnion:
        return FeatureUnion([
            (CHAR, TfidfVectorizer(analyzer="char_wb", ngram_range=self.char_ngram)),
            (WORD, TfidfVectorizer(analyzer="word", ngram_range=self.word_ngram)),
        ])

    def fit(
        self, texts: Sequence[str], y: Sequence[str], sample_weight: Sequence[float] | None = None
    ) -> None:
        if len(texts) != len(y):
            raise ValueError(f"{len(texts)} texts but {len(y)} labels")
        check_labels(y, self.labels)
        features = self._new_features()
        features.fit(list(dict.fromkeys(texts)))
        weights = balanced_sample_weight(y, sample_weight, self.labels)
        lr = LogisticRegression(C=self.C, max_iter=LR_MAX_ITER, random_state=self.seed)
        lr.fit(features.transform(list(texts)), list(y), sample_weight=weights)
        self._features, self._lr = features, lr

    def predict_proba(self, texts: Sequence[str]) -> list[ProbVector]:
        features, lr = self._fitted()
        if not texts:
            return []
        proba = lr.predict_proba(features.transform(list(texts)))
        return to_vectors(reorder(proba, [str(c) for c in lr.classes_], self.labels), self.labels)

    def token_contributions(self, text: str) -> list[tuple[str, float]]:
        """Per-word contributions (coefficient × tf-idf) to the argmax class, largest first.

        Each active feature's contribution goes to the words of `text` it comes from: a char n-gram is
        shared among the words that contain it (char_wb n-grams never cross words), and a word n-gram is
        split evenly among its words. Words are the lower-cased, whitespace-separated tokens of `text`;
        repeated words are merged. Empty text gives [].
        """
        features, lr = self._fitted()
        words = [w for w in _WS.split(text.lower()) if w]
        if not words:
            return []
        row = features.transform([text]).tocsr()
        cls_index = int(np.argmax(lr.predict_proba(row)[0]))
        coef = lr.coef_[cls_index] if lr.coef_.shape[0] > 1 else lr.coef_[0] * (1 if cls_index == 1 else -1)
        names = features.get_feature_names_out()
        char_vec: Any = features.transformer_list[0][1]
        word_vec: Any = features.transformer_list[1][1]
        char_analyzer, word_tokenizer = char_vec.build_analyzer(), word_vec.build_tokenizer()
        grams = {w: char_analyzer(w) for w in dict.fromkeys(words)}
        tokens = {w: word_tokenizer(w) for w in grams}
        totals: dict[str, float] = defaultdict(float)
        for col, value in zip(row.indices, row.data, strict=True):
            contribution = float(coef[col]) * float(value)
            prefix, _, feature = str(names[col]).partition("__")
            if prefix == CHAR:
                owners = {w: g.count(feature) for w, g in grams.items() if feature in g}
            else:
                parts = feature.split(" ")
                owners = {w: sum(t in parts for t in toks) for w, toks in tokens.items()}
                owners = {w: n for w, n in owners.items() if n}
            count = sum(owners.values())
            if not count:  # cannot happen for features analyzed from `text`; defensive
                continue
            for word, n in owners.items():
                totals[word] += contribution * n / count
        return sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))

    def save(self, dir: Path) -> None:
        """Write `<dir>/model.joblib` (vectorizer + LR) and `<dir>/meta.json`."""
        features, lr = self._fitted()
        meta = {"kind": KIND, "name": self.name, "target": self.target, "labels": list(self.labels),
                "char_ngram": list(self.char_ngram), "word_ngram": list(self.word_ngram), "C": self.C,
                "seed": self.seed}
        save_estimator(dir, {"features": features, "lr": lr}, meta)

    @classmethod
    def load(cls, dir: Path) -> TfidfLR:
        """Read a directory written by `save`. Raises ArtifactMissing / ArtifactVersionMismatch."""
        bundle, meta = load_estimator(dir, KIND)
        char_ngram, word_ngram = meta["char_ngram"], meta["word_ngram"]
        model = cls(meta["target"], (int(char_ngram[0]), int(char_ngram[1])),
                    (int(word_ngram[0]), int(word_ngram[1])), float(meta["C"]), int(meta["seed"]))
        model._features, model._lr = bundle["features"], bundle["lr"]
        return model

    def _fitted(self) -> tuple[FeatureUnion, LogisticRegression]:
        if self._features is None or self._lr is None:
            raise ValueError("TfidfLR is not fitted")
        return self._features, self._lr
