"""Hand-tune tau_faq, the FAQ answer cosine floor (P4.5, LD-11).

Runs the 30 questions in config/faq_tuning.yaml (15 answerable paraphrases, 15 not covered by the
FAQ) through the production path (frozen OnnxEncoder → VectorFAQRetriever → pgvector "faq", top 1
in the request language) and sweeps tau over 0.50..0.95:
  precision = correct answers / answers given;  recall = correct answers / answerable questions.
It picks the lowest tau with precision 1.00 (a wrong policy answer is worse than a ticket) and
writes it to config/hand_tuned.yaml; train.py copies it into config.json (LD-11).

Needs the frozen encoder and embedded FAQ rows (run scripts/seed_faq.py first).

    python scripts/tune_faq.py [--model-dir models/frozen/v1] [--dry-run]
      ->  chosen tau_faq=0.7x precision=1.00 recall=0.xx
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml

from campuspulse_ai.config.settings import Settings
from campuspulse_ai.domain.values import Lang

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = ROOT / "config" / "faq_tuning.yaml"
HAND_TUNED = ROOT / "config" / "hand_tuned.yaml"
GRID = [round(0.50 + 0.01 * i, 2) for i in range(46)]


@dataclass(frozen=True)
class Probe:
    text: str
    lang: Lang
    expect: frozenset[str]  # empty = unanswerable
    top_id: str | None = None
    top_score: float = 0.0


def sweep(probes: Sequence[Probe], grid: Sequence[float]) -> list[tuple[float, float, float]]:
    """(tau, precision, recall) per tau; precision is 1.0 when nothing is answered."""
    answerable = sum(1 for p in probes if p.expect)
    rows = []
    for tau in grid:
        answered = [p for p in probes if p.top_id is not None and p.top_score >= tau]
        correct = sum(1 for p in answered if p.top_id in p.expect)
        precision = correct / len(answered) if answered else 1.0
        recall = correct / answerable if answerable else 0.0
        rows.append((tau, precision, recall))
    return rows


def choose(rows: Sequence[tuple[float, float, float]]) -> tuple[float, float, float] | None:
    """Lowest tau with precision 1.0 that still answers something."""
    return next((row for row in rows if row[1] == 1.0 and row[2] > 0.0), None)


def write_tau(value: float, path: Path = HAND_TUNED) -> None:
    """Replace the tau_faq value in place, keeping the file's comments."""
    text = path.read_text(encoding="utf-8")
    new, n = re.subn(r"(?m)^(tau_faq:\s*)[0-9.]+", rf"\g<1>{value:.2f}", text)
    if n != 1:
        raise SystemExit(f"could not find a single tau_faq line in {path}")
    path.write_text(new, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model-dir", type=Path, default=ROOT / "models" / "frozen" / "v1")
    parser.add_argument(
        "--dry-run", action="store_true", help="print the sweep, do not write hand_tuned.yaml"
    )
    args = parser.parse_args()

    spec = yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))
    probes = [
        Probe(q["text"], Lang(q["lang"]), frozenset(spec["topics"][q["topic"]])) for q in spec["answerable"]
    ]
    probes += [Probe(q["text"], Lang(q["lang"]), frozenset()) for q in spec["unanswerable"]]

    config_path = args.model_dir / "config.json"
    if not config_path.is_file():
        print(f"missing {config_path}: build or fetch the frozen model first", file=sys.stderr)
        return 2
    dim = int(json.loads(config_path.read_text(encoding="utf-8"))["encoder"]["dim"])
    settings = Settings(_env_file=ROOT / ".env")  # type: ignore[call-arg]
    key = settings.supabase_service_role_key
    if not settings.supabase_url or key is None:
        print("needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY", file=sys.stderr)
        return 2
    try:
        from campuspulse_ai.adapters.models.encoder import OnnxEncoder  # P1.6
    except ImportError:
        print("OnnxEncoder (adapters/models/encoder.py, P1.6) is not available yet", file=sys.stderr)
        return 2
    from campuspulse_ai.adapters.faq.retriever import VectorFAQRetriever
    from campuspulse_ai.adapters.vectors.pgvector import PgVectorStore
    from supabase import create_client

    db = create_client(settings.supabase_url, key.get_secret_value())
    retriever = VectorFAQRetriever(PgVectorStore(db, dim), OnnxEncoder(args.model_dir / "encoder"))
    scored = []
    for p in probes:
        hits = retriever.search(p.text, p.lang, 1)
        scored.append(
            Probe(p.text, p.lang, p.expect, hits[0].id if hits else None, hits[0].score if hits else 0.0)
        )

    for p in scored:
        verdict = "ok " if (p.top_id in p.expect) else ("-- " if not p.expect else "MISS")
        print(f"{verdict} {p.top_score:.3f} [{p.lang}] {p.text}")
    rows = sweep(scored, GRID)
    for tau, precision, recall in rows:
        print(f"tau={tau:.2f} precision={precision:.2f} recall={recall:.2f}")
    best = choose(rows)
    if best is None:
        print("no tau reaches precision 1.00 with recall > 0; hand_tuned.yaml unchanged", file=sys.stderr)
        return 1
    tau, precision, recall = best
    if not args.dry_run:
        write_tau(tau)
    where = " (dry run, not written)" if args.dry_run else f" -> {HAND_TUNED.relative_to(ROOT)}"
    print(f"chosen tau_faq={tau:.2f} precision={precision:.2f} recall={recall:.2f}{where}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
