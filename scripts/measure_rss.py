"""Memory and latency budget of the AI service (P4.13, ARCHITECTURE §3.17), repeatable.

Sends N sequential `POST /v1/triage` calls to a running service (local uvicorn or the Docker image run
like Render Starter: `-m 512m --cpus 0.5`), reads `/health` `rss_mb` before the first call (idle) and
after every call, and reports the RSS idle/max and the latency p50/p95 against the budget
(RSS <= 400 MB, p95 <= 1500 ms). Writes `reports/render_rss.json`.

    python scripts/measure_rss.py --remote http://localhost:8000 --n 100 [--warmup 3] [--cleanup]

- Texts: the official validation file (`data/clean/val_clean.csv`, `text`; English and Arabic) plus a
  few Arabizi demo sentences, cycled in a fixed order. Never the holdouts.
- Every call uses the service token (`AI_SERVICE_TOKEN` from the env or `.env`) and the alias
  `rss-<run>-<i>`, marked `simulated`. The calls write real rows: run the service with
  `ENABLE_SINKS=false` (no Linear issues), no Gmail password (no email) and `SLA_SCAN_MINUTES=0`.
- `--cleanup` deletes this run's rows afterwards (requests and their cascade, notifications, outbox and
  events) with `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`.
- The first `--warmup` calls are sent and timed but left out of the percentiles (one-off lazy loads).
- `--labels <csv>` writes each call's status, labels, sets and flags, so two runs (e.g. two images over
  the same live memory) can be compared byte for byte.

Exit codes: 0 within budget; 1 over budget; 2 bad arguments or the service is unreachable.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "data" / "clean" / "val_clean.csv"
DEFAULT_OUT = ROOT / "reports" / "render_rss.json"
REFUSED_PARTS = ("our_test", "robustness", "hidden_test")
BUDGET_RSS_MB = 400.0
BUDGET_P95_MS = 1500.0
PERCENT = 100
P95 = 95
TIMEOUT_S = 60.0
LABEL_COLUMNS = ("call", "status", "category", "category_set", "priority", "priority_set", "flags")
ARABIZI = (
    "el wifi msh shaghal fi el maktabe, wala ishi bifta7",
    "ma3i mushkle bel tasjeel, el portal ma bkhalini a7ot mada",
    "el bus ma ija el yom, w 3indi imti7an el sa3a 10",
)


def load_texts(path: Path) -> list[str]:
    """Validation texts (EN + AR) interleaved with the Arabizi sentences. Refuses holdout paths."""
    if any(part in str(path) for part in REFUSED_PARTS):
        raise ValueError(f"refused: {path} is a holdout; use the official validation file")
    with path.open(encoding="utf-8-sig", newline="") as fh:
        rows = [r["text"] for r in csv.DictReader(fh) if r.get("text", "").strip()]
    if not rows:
        raise ValueError(f"{path}: no `text` rows")
    out: list[str] = []
    for i, text in enumerate(rows):
        out.append(text)
        if i % len(ARABIZI) == 0:
            out.append(ARABIZI[(i // len(ARABIZI)) % len(ARABIZI)])
    return out


def percentile(values: list[float], pct: int) -> float:
    """Nearest-rank percentile (no interpolation), so p95 of 100 calls is the 95th slowest."""
    ordered = sorted(values)
    rank = max(1, -(-pct * len(ordered) // PERCENT))
    return ordered[rank - 1]


def env_value(name: str) -> str:
    return os.environ.get(name) or str(dotenv_values(ROOT / ".env").get(name) or "")


def rss(client: httpx.Client) -> float | None:
    r = client.get("/health")
    value = r.json().get("rss_mb") if r.status_code == httpx.codes.OK else None
    return float(value) if isinstance(value, int | float) else None


def run(args: argparse.Namespace) -> dict[str, Any]:
    token = env_value("AI_SERVICE_TOKEN")
    if not token:
        raise ValueError("AI_SERVICE_TOKEN is not set (env or .env)")
    texts = load_texts(args.csv)
    run_id = uuid.uuid4().hex[:8]
    client = httpx.Client(base_url=args.remote.rstrip("/"), timeout=TIMEOUT_S,
                          headers={"Authorization": f"Bearer {token}"})  # fmt: skip
    idle = rss(client)
    started = datetime.now(UTC).isoformat()
    latencies: list[float] = []
    rss_seen: list[float] = [idle] if idle is not None else []
    statuses: dict[str, int] = {}
    labels: list[list[str]] = []
    for i in range(args.warmup + args.n):
        body = {"text": texts[i % len(texts)], "student_alias": f"rss-{run_id}-{i:03d}", "simulated": True}
        t0 = time.perf_counter()
        r = client.post("/v1/triage", json=body)
        ms = (time.perf_counter() - t0) * 1000
        if r.status_code != httpx.codes.OK:
            raise RuntimeError(f"call {i}: HTTP {r.status_code} {r.text[:200]}")
        out = r.json()
        statuses[out["status"]] = statuses.get(out["status"], 0) + 1
        labels.append(_labels(i, out))
        if i >= args.warmup:
            latencies.append(ms)
        value = rss(client)
        if value is not None:
            rss_seen.append(value)
    result = {
        "measured_at": started,
        "remote": args.remote,
        "n": args.n,
        "warmup": args.warmup,
        "run": run_id,
        "rss_mb_idle": round(idle, 1) if idle is not None else None,
        "rss_mb_max": round(max(rss_seen), 1) if rss_seen else None,
        "rss_mb_end": round(rss_seen[-1], 1) if rss_seen else None,
        "p50_ms": round(statistics.median(latencies), 1),
        "p95_ms": round(percentile(latencies, P95), 1),
        "max_ms": round(max(latencies), 1),
        "statuses": statuses,
        "budget": {"rss_mb": BUDGET_RSS_MB, "p95_ms": BUDGET_P95_MS},
        "label": args.label,
    }
    result["ok"] = bool(
        result["rss_mb_max"] is not None
        and result["rss_mb_max"] <= BUDGET_RSS_MB
        and result["p95_ms"] <= BUDGET_P95_MS
    )
    if args.labels is not None:
        with args.labels.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh, lineterminator="\n")
            writer.writerow(LABEL_COLUMNS)
            writer.writerows(labels)
    if args.cleanup:
        result["cleaned"] = cleanup(run_id, started)
    return result


def _labels(i: int, out: dict[str, Any]) -> list[str]:
    """One `--labels` row: what the service decided for call `i` (compare two runs with `cmp`)."""
    category, priority = out.get("category") or {}, out.get("priority") or {}
    return [
        str(i),
        str(out["status"]),
        str(category.get("label") or ""),
        "|".join(category.get("set") or []),
        str(priority.get("label") or ""),
        "|".join(priority.get("set") or []),
        "|".join(out.get("flags") or []),
    ]


def cleanup(run_id: str, since: str) -> dict[str, int]:
    """Delete this run's rows (service role). Returns the counts per table."""
    from supabase import create_client

    url, key = env_value("SUPABASE_URL"), env_value("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise ValueError("--cleanup needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
    db = create_client(url, key)
    prefix = f"rss-{run_id}-%"
    requests = db.table("requests").select("id").like("alias", prefix).execute().data
    ids = [r["id"] for r in requests]
    tickets = db.table("tickets").select("id").in_("request_id", ids).execute().data if ids else []
    entities = [f"request:{i}" for i in ids] + [f"ticket:{t['id']}" for t in tickets]
    counts = {"events": 0, "notifications": 0}
    for k in range(0, len(entities), 50):
        part = entities[k : k + 50]
        deleted = db.table("events").delete().gte("at", since).in_("entity", part).execute().data
        counts["events"] += len(deleted)
    for k in range(0, len(ids), 50):
        part = ids[k : k + 50]
        notes = db.table("notifications").delete().gte("created_at", since)
        counts["notifications"] += len(notes.in_("payload->>request_id", part).execute().data)
    counts["notifications"] += len(db.table("notifications").delete().like("alias", prefix).execute().data)
    counts["outbox"] = len(db.table("outbox").delete().like("to_address", prefix).execute().data)
    counts["requests"] = len(db.table("requests").delete().like("alias", prefix).execute().data)
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--remote", default="http://localhost:8000", help="base URL of the running service")
    parser.add_argument("--n", type=int, default=100, help="measured /v1/triage calls")
    parser.add_argument("--warmup", type=int, default=3, help="untimed calls first (left out of percentiles)")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="texts (`text` column)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="JSON report path")
    parser.add_argument("--label", default="", help="free text stored in the report (e.g. the image tag)")
    parser.add_argument("--cleanup", action="store_true", help="delete this run's rows afterwards")
    parser.add_argument("--labels", type=Path, default=None, help="write each call's decision to this CSV")
    args = parser.parse_args(argv)
    if args.n < 1 or args.warmup < 0:
        print("--n must be >= 1 and --warmup >= 0", file=sys.stderr)
        return 2
    try:
        result = run(args)
    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
        print(f"measure_rss: {exc}", file=sys.stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    verdict = "OK" if result["ok"] else "FAIL"
    print(
        f"{verdict} rss_mb idle={result['rss_mb_idle']} max={result['rss_mb_max']} "
        f"(budget {BUDGET_RSS_MB:.0f}) p50_ms={result['p50_ms']} p95_ms={result['p95_ms']} "
        f"(budget {BUDGET_P95_MS:.0f}) n={args.n} statuses={result['statuses']} -> {args.out}"
    )
    if "cleaned" in result:
        print(f"cleaned {result['cleaned']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
