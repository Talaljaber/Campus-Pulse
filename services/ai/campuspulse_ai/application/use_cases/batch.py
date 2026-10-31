"""BatchCsvUseCase: `POST /v1/batch`, CSV in, predictions CSV out (SPEC §5.5, P4.12).

The CSV format is the `predict.py` contract (ARCHITECTURE §2.5):
- input: UTF-8 (a BOM is accepted, `utf-8-sig`), a header with at least `request_id` and `text`
  (extra columns ignored), values read as strings;
- output: exactly `request_id,category,priority`, the input row order, UTF-8 without BOM, `\\n` line
  endings, minimal quoting (a field is quoted only when it holds a comma, quote or newline).

`read_batch_csv` and `write_predictions_csv` are public so `predict.py` can write the same bytes
(change request to the ML stream).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence

from campuspulse_ai.application import dto
from campuspulse_ai.application.use_cases.ports import BatchLabeler
from campuspulse_ai.domain.errors import InvalidInput

INPUT_ENCODING = "utf-8-sig"
OUTPUT_ENCODING = "utf-8"
LINE_TERMINATOR = "\n"


def read_batch_csv(data: bytes, *, max_rows: int) -> list[tuple[str, str]]:
    """`[(request_id, text)]` in file order, values exactly as written (like pandas `dtype=str,
    keep_default_na=False`: nothing is stripped or converted).

    Raises `InvalidInput` for a file that is not UTF-8, has no header, lacks a required column or has
    more than `max_rows` rows.
    """
    try:
        text = data.decode(INPUT_ENCODING)
    except UnicodeDecodeError as exc:
        raise InvalidInput("the CSV is not UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    columns = set(reader.fieldnames or ())
    missing = [c for c in dto.BATCH_INPUT_COLUMNS if c not in columns]
    if missing:
        raise InvalidInput(f"the CSV needs the columns {list(dto.BATCH_INPUT_COLUMNS)}; missing {missing}")
    rows: list[tuple[str, str]] = []
    for record in reader:
        if len(rows) >= max_rows:
            raise InvalidInput(f"the CSV has more than {max_rows} rows")
        rows.append((record.get("request_id") or "", record.get("text") or ""))
    return rows


def write_predictions_csv(rows: Sequence[tuple[str, str, str]]) -> bytes:
    """The predictions CSV bytes (header `dto.BATCH_CSV_COLUMNS`, LF, no BOM, minimal quoting)."""
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator=LINE_TERMINATOR, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(dto.BATCH_CSV_COLUMNS)
    writer.writerows(rows)
    return out.getvalue().encode(OUTPUT_ENCODING)


class BatchCsvUseCase:
    """`run(data, use_llm=False) -> bytes`: parse, label every row with `BatchLabeler`, write the CSV.

    No rows are written and no notifications are sent (batch semantics: no clarification, no actions).
    Errors: `InvalidInput` (bad CSV or too many rows, 422); `ArtifactError` from the labeler (503);
    `RuntimeError` if the labeler breaks its contract (rows lost or reordered, 500).
    """

    def __init__(self, labeler: BatchLabeler, *, max_rows: int) -> None:
        self._labeler = labeler
        self._max_rows = max_rows

    def run(self, data: bytes, *, use_llm: bool = False) -> bytes:
        rows = read_batch_csv(data, max_rows=self._max_rows)
        labelled = self._labeler.label(rows, use_llm=use_llm)
        if [r[0] for r in labelled] != [r[0] for r in rows]:
            raise RuntimeError("the batch labeler returned rows in a different order or number")
        return write_predictions_csv(labelled)
