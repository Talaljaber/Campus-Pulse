"""Pulse simulator (P4.10, X4.3): replay a burst of fictional reports and watch an incident form.

Every request it writes is SIMULATED TRAFFIC: aliases `sim-0N`, `requests.simulated = true`.

--mode direct (default until P4.14): writes each report straight through SupabaseRepository and
  PgVectorStore (request, prediction, "requests" embedding) and runs WindowedCentroidDetector,
  i.e. steps [12b]-[13] of the triage flow without the classifier. Category/priority come from
  the scenario file. Embeddings use the frozen OnnxEncoder when `<model-dir>/encoder` exists,
  else synthetic topic vectors (one topic per scenario, small per-report noise), labelled as such.
--mode api (P4.10, the default when --api is given): POSTs each report to {api}/v1/triage with the
  service token (AI_SERVICE_TOKEN), `student_alias=sim-0N`, `simulated=true` and the scenario's
  building/room, so the real classifier, detector (tau_inc from config/hand_tuned.yaml, D-015),
  incident ticket and broadcast run. After each post it prints GET /v1/incidents?open=1.

    python scripts/simulate_pulse.py --api http://localhost:8000 [--scenario ...] [--interval 4]
      ->  [3/8] sim-03 (arabizi) ... -> incident created: <uuid> building=M reports=3 ticket=<id>
    python scripts/simulate_pulse.py --mode direct --scenario config/simulation/wifi_m.yaml [--reset]
      ->  incident created: <uuid> building=M category=IT Support reports=3
          ... priority bumped -> high
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from campuspulse_ai.config.settings import Settings
from campuspulse_ai.domain.entities import CoreResult, Prediction, Request
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS, Category, Priority
from campuspulse_ai.domain.values import (
    ArtifactVersion,
    EvidenceVector,
    GuardVerdict,
    Lang,
    Location,
    Money,
    NormalizedRequest,
    PredictionSet,
    ProbVector,
    RequestStatus,
    Tier,
    VectorItem,
)

ROOT = Path(__file__).resolve().parents[1]
DIM = 384
HAND_TUNED = yaml.safe_load((ROOT / "config" / "hand_tuned.yaml").read_text(encoding="utf-8"))
BANNER = "=== SIMULATED TRAFFIC (fictional students sim-0N; requests.simulated = true) ==="


class UtcClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


def guess_lang(text: str) -> Lang:
    if any("؀" <= ch <= "ۿ" for ch in text):
        return Lang.AR
    return (
        Lang.ARABIZI if any(tok in text.lower() for tok in ("msh", "kaman", "bala", "wala", "7")) else Lang.EN
    )


def one_hot(labels: tuple[str, ...], label: str) -> ProbVector:
    return ProbVector(tuple(1.0 if x == label else 0.0 for x in labels), labels)


def simulated_prediction(request_id: str, category: Category, priority: Priority) -> Prediction:
    core = CoreResult(
        p_cat=one_hot(CATEGORY_LABELS, str(category)),
        p_pri=one_hot(PRIORITY_LABELS, str(priority)),
        per_model={},
        flags=frozenset(),
        set_cat=PredictionSet(frozenset({str(category)})),
        set_pri=PredictionSet(frozenset({str(priority)})),
        ood_score=0.0,
        neighbors=(),
        evidence=EvidenceVector(flags={}),
        guard=GuardVerdict(kind="none"),
        safety=False,
        floors_applied=(),
        tier=Tier.HUMAN,
        latency_ms=0,
        artifact=ArtifactVersion("simulated", "0" * 64),
    )
    return Prediction(
        "", request_id, category, priority, core, Tier.HUMAN, set(), None, Money(0.0), "simulated"
    )


class SyntheticEncoder:
    """One random topic per scenario plus small per-report noise (cosine ≈ 0.99 within a topic)."""

    model_id = "synthetic-topic"
    dim = DIM

    def __init__(self, topic: str) -> None:
        self._topic = random.Random(topic)
        self._base = [self._topic.gauss(0, 1) for _ in range(DIM)]

    def encode(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            noise = random.Random(text)
            v = [b + 0.05 * noise.gauss(0, 1) for b in self._base]
            n = sum(x * x for x in v) ** 0.5
            out.append([x / n for x in v])
        return out


def load_encoder(model_dir: Path, topic: str) -> tuple[Any, str]:
    if (model_dir / "encoder").is_dir():
        try:
            from campuspulse_ai.adapters.models.encoder import OnnxEncoder  # P1.6

            return OnnxEncoder(model_dir / "encoder"), "frozen OnnxEncoder"
        except ImportError:
            pass
    return SyntheticEncoder(topic), "SYNTHETIC topic vectors (frozen encoder not available)"


def run_direct(args: argparse.Namespace, scenario: dict[str, Any]) -> int:
    from campuspulse_ai.adapters.pulse.incident_detector import WindowedCentroidDetector
    from campuspulse_ai.adapters.store.supabase_store import SupabaseRepository
    from campuspulse_ai.adapters.vectors.pgvector import PgVectorStore
    from supabase import create_client

    settings = Settings(_env_file=ROOT / ".env")  # type: ignore[call-arg]
    key = settings.supabase_service_role_key
    if not settings.supabase_url or key is None:
        print("needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY", file=sys.stderr)
        return 2
    db = create_client(settings.supabase_url, key.get_secret_value())
    clock = UtcClock()
    repo = SupabaseRepository(db, clock)
    vectors = PgVectorStore(db, DIM)
    detector = WindowedCentroidDetector(
        repo, vectors, clock, tau_inc=args.tau, window_min=settings.incident_window_min,
        min_reports=args.min_reports, bump_at=args.bump_at,
    )  # fmt: skip
    building, category = str(scenario["building"]), Category(scenario["category"])
    encoder, encoder_name = load_encoder(args.model_dir, f"{building}:{category}")

    if args.reset:
        since = clock.now() - timedelta(minutes=settings.incident_window_min)
        db.table("requests").delete().eq("simulated", True).like("alias", "sim-%").execute()
        db.table("incidents").delete().eq("building_id", building).eq("category", str(category)).eq(
            "status", "open"
        ).gte("opened_at", since.isoformat()).execute()
        print("reset: removed earlier simulated requests and this window's open incident")

    print(BANNER)
    print(f"mode=direct  building={building}  category={category}  tau_inc={args.tau}")
    print(f"embeddings: {encoder_name}")
    priority_seen: Priority | None = None
    reports = scenario["reports"]
    for n, item in enumerate(reports, start=1):
        text = str(item["text"])
        lang = guess_lang(text)
        now = clock.now()
        location = Location(building, scenario.get("room"), "picked")
        is_arabizi = lang == Lang.ARABIZI
        normalized = NormalizedRequest(
            text, text, text.lower(), text.lower(), lang, is_arabizi, False, False, location
        )
        req = repo.save_request(
            Request("", f"sim-{n:02d}", text, normalized, "text", RequestStatus.DECIDED, now, None)
        )
        db.table("requests").update({"simulated": True}).eq("id", req.id).execute()
        priority = Priority(item.get("priority", "medium"))
        pred = repo.save_prediction(simulated_prediction(req.id, category, priority))
        embedding = encoder.encode([text])[0]
        meta = {"building_id": building, "room": location.room, "category": str(category),
                "priority": str(priority), "created_at": now.isoformat()}  # fmt: skip
        vectors.upsert("requests", [VectorItem(req.id, tuple(embedding), text, lang, meta)])
        decision = detector.detect(req, pred, embedding)

        line = f"[{n}/{len(reports)}] sim-{n:02d} ({lang}) {text!r}"
        if decision.incident is None:
            print(f"{line} -> no incident yet ({len(decision.members)} similar)")
        else:
            inc = decision.incident
            verb = "incident created" if decision.kind == "new" else "attached to incident"
            print(f"{line} -> {verb}: {inc.id} building={inc.building} category={inc.category} "
                  f"reports={inc.report_count} priority={inc.priority}")  # fmt: skip
            if priority_seen is not None and inc.priority.rank > priority_seen.rank:
                print(f"    priority bumped -> {inc.priority}")
            priority_seen = inc.priority
        if n < len(reports):
            time.sleep(args.interval)
    print(BANNER)
    return 0


def run_api(args: argparse.Namespace, scenario: dict[str, Any]) -> int:
    """Post the scenario through /v1/triage (module docstring, --mode api)."""
    import os

    import httpx

    settings = Settings(_env_file=ROOT / ".env")  # type: ignore[call-arg]
    token = os.environ.get("AI_SERVICE_TOKEN") or (
        settings.ai_service_token.get_secret_value() if settings.ai_service_token else ""
    )
    if not args.api or not token:
        print("--mode api needs --api <base url> and AI_SERVICE_TOKEN", file=sys.stderr)
        return 2
    client = httpx.Client(base_url=args.api.rstrip("/"), timeout=60.0,
                          headers={"Authorization": f"Bearer {token}"})  # fmt: skip
    building = str(scenario["building"])
    location = {"building": building, "room": scenario.get("room")}
    print(BANNER)
    print(f"mode=api  api={args.api}  building={building}")
    seen: dict[str, int] = {}
    reports = scenario["reports"]
    for n, item in enumerate(reports, start=1):
        text = str(item["text"])
        alias = f"sim-{n:02d}"
        body = {"text": text, "student_alias": alias, "simulated": True, "location": location}
        r = client.post("/v1/triage", json=body)
        if r.status_code != httpx.codes.OK:
            print(f"[{n}/{len(reports)}] {alias} -> HTTP {r.status_code}: {r.text[:200]}")
            return 1
        out = r.json()
        action = out.get("action") or {}
        line = (f"[{n}/{len(reports)}] {alias} ({out['lang']}) {text!r} -> {out['status']}"
                f" {(out.get('category') or {}).get('label')} action={action.get('type')}")  # fmt: skip
        print(line)
        listed = client.get("/v1/incidents", params={"open": 1})
        for inc in listed.json() if listed.status_code == httpx.codes.OK else []:
            if inc["building"] != building:
                continue
            before = seen.get(inc["id"])
            verb = "incident created" if before is None else "incident"
            if before != inc["report_count"]:
                print(f"    {verb}: {inc['id']} building={inc['building']} category={inc['category']} "
                      f"reports={inc['report_count']} priority={inc['priority']} ticket={inc['ticket_id']} "
                      f"simulated={inc['simulated']}")  # fmt: skip
            seen[inc["id"]] = inc["report_count"]
        if n < len(reports):
            time.sleep(args.interval)
    print(BANNER)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scenario", type=Path, default=ROOT / "config" / "simulation" / "wifi_m.yaml")
    parser.add_argument("--mode", choices=("direct", "api"), default=None,
                        help="api (default with --api) or direct (writes through Supabase)")
    parser.add_argument("--api", help="AI service base URL (api mode)")
    parser.add_argument("--interval", type=float, default=4.0, help="seconds between reports")
    parser.add_argument("--model-dir", type=Path, default=ROOT / "models" / "frozen" / "v1")
    parser.add_argument(
        "--tau", type=float, default=float(HAND_TUNED["tau_inc"]),
        help="direct mode only: tau_inc (default config/hand_tuned.yaml, D-015)",
    )
    parser.add_argument("--min-reports", type=int, default=3)
    parser.add_argument("--bump-at", type=int, default=6)
    parser.add_argument("--reset", action="store_true", help="delete earlier simulated requests first")
    args = parser.parse_args()
    scenario = yaml.safe_load(args.scenario.read_text(encoding="utf-8"))
    mode = args.mode or ("api" if args.api else "direct")
    if mode == "api":
        return run_api(args, scenario)
    return run_direct(args, scenario)


if __name__ == "__main__":
    raise SystemExit(main())
