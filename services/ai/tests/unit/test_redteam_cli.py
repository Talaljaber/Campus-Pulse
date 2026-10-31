"""P4.11: the offline red-team CLI (`evaluate.py --redteam`) and `composition.redteam`.

The core is injected (`core_factory`) so these tests need no model files (the encoder is fetched, not
committed); the real default factory (`build_offline`) is only checked to fail cleanly on a model
directory that is absent.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from fixtures.redteam import POLICY, KeywordCore, seed_csv

from campuspulse_ai.application.use_cases.ports import TriageClassifier
from campuspulse_ai.composition.redteam import CoreFactory
from campuspulse_ai.domain.ports import DecisionPolicy
from campuspulse_ai.frameworks.cli import evaluate


def factory(core: KeywordCore) -> CoreFactory:
    def build(model_dir: Path) -> tuple[TriageClassifier, DecisionPolicy]:
        return core, POLICY

    return build


def run_cli(tmp_path: Path, *extra: str, core: KeywordCore | None = None) -> int:
    argv = ["--redteam", "--seed-csv", str(seed_csv(tmp_path)), "--out-dir", str(tmp_path / "out"), *extra]
    return evaluate.main(argv, core_factory=factory(core or KeywordCore()))


def test_the_cli_writes_the_report_and_the_failure_candidates(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_cli(tmp_path, "--n", "40", "--seed", "42") == 0
    out = capsys.readouterr().out
    assert out.startswith("scorecard overall=") and "n=40" in out and "written " in out
    assert "label_stability=" in out and "priority_gaming_resistance=1.00" in out
    (report_path,) = (tmp_path / "out").glob("2*.json")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert (report["n"], report["seed"], len(report["items"])) == (40, 42, 40)
    assert report["source"]["seed_csv"].endswith("seeds.csv") and report["source"]["memory"] is False
    assert set(report["properties"]) == {
        "label_stability",
        "priority_gaming_resistance",
        "injection_resistance",
    }
    (cand_path,) = (tmp_path / "out").glob("candidates_*.csv")
    with cand_path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == len(report["failures"]) > 0
    assert all(r["needs_human_check"] == "True" and r["author_method"] == "perturb" for r in rows)
    assert rows[0]["request_id"] == "CAND-001"


def test_same_seed_same_report(tmp_path: Path) -> None:
    def items(sub: str, seed: str) -> object:
        base = tmp_path / sub
        base.mkdir()
        assert run_cli(base, "--n", "30", "--seed", seed) == 0
        (path,) = (base / "out").glob("2*.json")
        report = json.loads(path.read_text(encoding="utf-8"))
        return report["items"], report["by_style"], report["overall"]

    assert items("a", "42") == items("b", "42")
    assert items("c", "42") != items("d", "7")


@pytest.mark.parametrize(
    ("args", "code", "message"),
    [
        (["--n", "201"], 4, "between 1 and 200"),
        (["--styles", "typos,sarcasm"], 4, "sarcasm"),
    ],
)
def test_bad_input_exits_4(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], args: list[str], code: int, message: str
) -> None:
    assert run_cli(tmp_path, *args) == code
    assert message in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


def test_holdout_seed_file_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    argv = ["--redteam", "--seed-csv", str(tmp_path / "data" / "our_test" / "our_test.csv")]
    assert evaluate.main(argv, core_factory=factory(KeywordCore())) == 4
    assert "holdout" in capsys.readouterr().err


def test_without_a_model_the_cli_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    argv = ["--redteam", "--n", "5", "--model-dir", str(tmp_path / "no-model"), "--out-dir", str(tmp_path)]
    assert evaluate.main(argv) == 2
    assert "no usable model" in capsys.readouterr().err


def test_evaluate_without_a_mode_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        evaluate.main([])
    assert exc.value.code == 2 and "--redteam" in capsys.readouterr().err
