"""`predict.py` against the real frozen v1 (P1.17, ARCHITECTURE §3.1). Needs the fetched encoder."""

from __future__ import annotations

import csv
import shutil
import socket
from pathlib import Path

import pytest

from campuspulse_ai.config.paths import DATA_CLEAN, DATA_RAW, MODELS_FROZEN
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS
from campuspulse_ai.frameworks.cli.predict import main

pytestmark = pytest.mark.artifacts
HEADER = ["request_id", "category", "priority"]


def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*_a: object, **_k: object) -> None:
        raise OSError("network disabled in test")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)


def _read(path: Path) -> list[list[str]]:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw
    return list(csv.reader(raw.decode("utf-8").splitlines()))


def _ids(path: Path) -> list[str]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return [r["request_id"] for r in csv.DictReader(fh)]


def test_val_clean_offline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                           capsys: pytest.CaptureFixture[str]) -> None:
    _no_network(monkeypatch)
    out = tmp_path / "pred.csv"
    assert main(["--input", str(DATA_CLEAN / "val_clean.csv"), "--output", str(out)]) == 0
    rows = _read(out)
    assert rows[0] == HEADER and len(rows) == 63
    assert [r[0] for r in rows[1:]] == _ids(DATA_CLEAN / "val_clean.csv")
    assert {r[1] for r in rows[1:]} <= set(CATEGORY_LABELS)
    assert {r[2] for r in rows[1:]} <= set(PRIORITY_LABELS)
    assert "wrote 62 rows" in capsys.readouterr().out


def test_raw_validation_with_bom(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _no_network(monkeypatch)
    assert (DATA_RAW / "validation.csv").read_bytes().startswith(b"\xef\xbb\xbf")
    out = tmp_path / "pred.csv"
    assert main(["--input", str(DATA_RAW / "validation.csv"), "--output", str(out), "--debug"]) == 0
    rows = _read(out)
    assert rows[0][:3] == HEADER and "p_category" in rows[0]
    assert [r[0] for r in rows[1:]] == _ids(DATA_RAW / "validation.csv")


def test_exit_2_without_encoder(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    src = MODELS_FROZEN / "v1"
    dst = tmp_path / "v1"
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("encoder"))
    out = tmp_path / "pred.csv"
    code = main(["--input", str(DATA_RAW / "validation.csv"), "--output", str(out), "--model-dir", str(dst)])
    assert code == 2 and not out.exists()
    assert "python scripts/fetch_models.py" in capsys.readouterr().err


def test_predict_bytes_equal_v1_batch(tmp_path: Path) -> None:
    """predict.py and POST /v1/batch write byte-identical predictions (shared reader and writer)."""
    from campuspulse_ai.application.use_cases.batch import BatchCsvUseCase
    from campuspulse_ai.composition.offline import build_offline

    out = tmp_path / "pred.csv"
    assert main(["--input", str(DATA_RAW / "validation.csv"), "--output", str(out)]) == 0
    api = BatchCsvUseCase(build_offline(MODELS_FROZEN).labeler, max_rows=10_000)
    assert api.run((DATA_RAW / "validation.csv").read_bytes()) == out.read_bytes()


def test_exit_4_missing_text_column(tmp_path: Path) -> None:
    bad = tmp_path / "bad.csv"
    bad.write_text("request_id,body\nX-1,hello\n", encoding="utf-8")
    assert main(["--input", str(bad), "--output", str(tmp_path / "p.csv")]) == 4


def test_exit_3_use_llm_without_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)  # Settings reads ".env" from the cwd; keep a local dev key out of this test
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    args = ["--input", str(DATA_RAW / "validation.csv"), "--output", str(tmp_path / "p.csv"), "--use-llm"]
    assert main(args) == 3


@pytest.mark.slow
def test_predict_speed_1000_rows(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with (DATA_RAW / "train.csv").open(encoding="utf-8-sig", newline="") as fh:
        texts = [r["text"] for r in csv.DictReader(fh)]
    big = tmp_path / "big.csv"
    with big.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["request_id", "text"])
        for i in range(1000):
            # a distinct text per row (worst case: duplicate texts are scored once per batch)
            w.writerow([f"S-{i:04d}", f"{texts[i % len(texts)]} (ref {i})"])
    assert main(["--input", str(big), "--output", str(tmp_path / "p.csv")]) == 0
    seconds = float(capsys.readouterr().out.rsplit(", ", 1)[1].split(" s")[0])
    assert seconds < 60
