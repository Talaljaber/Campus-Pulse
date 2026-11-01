"""`CsvCachedTranslator`: a training-time translation cache (P2.15).

Wraps a `Translator` with the CSV of `reports/translate_test/translations.csv` (source, translation, model id,
revision, backend, beam). Rows of another model or revision are ignored. A text found in the table is never
re-translated, so a retrain reproduces the experiment's translations exactly; new texts go to the inner
translator and `save()` appends them. Read-only when `inner` is None (a missing text then raises).
"""

from __future__ import annotations

import csv
from collections.abc import Sequence
from pathlib import Path

from campuspulse_ai.domain.errors import ArtifactMissing
from campuspulse_ai.domain.ports import Translator

HEADER = ["source", "translation", "model_id", "revision", "backend", "beam"]


class CsvCachedTranslator:
    """Implements `domain.ports.Translator` over a CSV table and an optional inner translator."""

    def __init__(self, path: Path, inner: Translator | None, model_id: str, revision: str) -> None:
        self.path = Path(path)
        self._inner = inner
        self.model_id = model_id
        self.revision = revision
        self.table: dict[str, str] = {}
        self.dirty = False
        if self.path.is_file():
            with self.path.open(encoding="utf-8", newline="") as fh:
                for row in csv.DictReader(fh):
                    if row["model_id"] == model_id and row["revision"] == revision:
                        self.table[row["source"]] = row["translation"]

    def translate(self, texts: Sequence[str]) -> list[str]:
        missing = list(dict.fromkeys(t for t in texts if t not in self.table))
        if missing:
            if self._inner is None:
                n = len(missing)
                raise ArtifactMissing(f"{n} texts are not in {self.path} and no translator is loaded")
            self.table.update(zip(missing, self._inner.translate(missing), strict=True))
            self.dirty = True
        return [self.table[t] for t in texts]

    def save(self) -> None:
        """Rewrite the CSV, sorted by source, with the model id and revision of every row."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh, lineterminator="\n")
            writer.writerow(HEADER)
            for source in sorted(self.table):
                row = [source, self.table[source], self.model_id, self.revision, "ctranslate2-int8", 1]
                writer.writerow(row)
        self.dirty = False
