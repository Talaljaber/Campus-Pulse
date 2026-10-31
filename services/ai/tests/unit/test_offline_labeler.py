"""`OfflineBatchLabeler`: the `/v1/batch` port over `BatchPredictUseCase` (lead request, batch 3)."""

from __future__ import annotations

from pathlib import Path

from fixtures.fakes import HashingEncoder

from campuspulse_ai.application.use_cases.batch import BatchCsvUseCase
from campuspulse_ai.application.use_cases.ports import BatchLabeler
from campuspulse_ai.composition.offline import BatchRow, build_offline
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS


def test_offline_labeler_is_a_batch_labeler(tiny_model_dir: Path) -> None:
    container = build_offline(tiny_model_dir, encoder_override=HashingEncoder())
    labeler = container.labeler
    assert isinstance(labeler, BatchLabeler)
    rows = [("A", "The bus is late"), ("B", "   "), ("C", "my exam portal crashed today")]
    out = labeler.label(rows, use_llm=False)
    assert [r[0] for r in out] == ["A", "B", "C"]
    assert all(c in CATEGORY_LABELS and p in PRIORITY_LABELS for _, c, p in out)
    expected = [(p.request_id, p.category, p.priority)
                for p in container.batch.run([BatchRow(*r) for r in rows])]
    assert out == expected
    csv_bytes = BatchCsvUseCase(labeler, max_rows=10).run(b"request_id,text\nA,The bus is late\n")
    assert csv_bytes.startswith(b"request_id,category,priority\nA,")

