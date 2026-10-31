"""Embed FAQ questions with the frozen encoder and store them in pgvector (P4.3).

The FAQ text comes from supabase/seed/04_faq_text.sql. This script fills `faq.embedding` for
rows that have none (or every row with --all), using the same OnnxEncoder as the live service,
so FAQ search lives in the encoder's space (ARCHITECTURE §3.18).

Dim guard: it refuses to run unless `<model-dir>/config.json` `encoder.dim` equals the database
`vector_dim()`. Uses SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY (env or repo `.env`).

    python scripts/seed_faq.py [--model-dir models/frozen/v1] [--all]
      ->  embedded 28 faq rows (dim=384)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

from campuspulse_ai.config.settings import Settings
from campuspulse_ai.domain.values import Lang, VectorItem

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model-dir", type=Path, default=ROOT / "models" / "frozen" / "v1")
    parser.add_argument("--all", action="store_true", help="re-embed every row, not only rows without one")
    args = parser.parse_args()

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

    from supabase import create_client

    client = create_client(settings.supabase_url, key.get_secret_value())
    db_dim = client.rpc("vector_dim").execute().data
    if db_dim != dim:
        print(
            f"refusing: config.json encoder.dim={dim} but the database vector_dim()={db_dim}", file=sys.stderr
        )
        return 1

    query = client.table("faq").select("id,lang,question,answer,source_url,is_demo").order("id")
    if not args.all:
        query = query.is_("embedding", "null")
    rows = cast(list[dict[str, Any]], query.execute().data)
    if not rows:
        print(f"embedded 0 faq rows (dim={dim}); nothing to do")
        return 0

    try:
        from campuspulse_ai.adapters.models.encoder import OnnxEncoder  # P1.6
    except ImportError:
        print("OnnxEncoder (adapters/models/encoder.py, P1.6) is not available yet", file=sys.stderr)
        return 2
    from campuspulse_ai.adapters.vectors.pgvector import PgVectorStore

    encoder = OnnxEncoder(args.model_dir / "encoder")
    embeddings = encoder.encode([row["question"] for row in rows])
    store = PgVectorStore(client, dim)
    store.upsert(
        "faq",
        [
            VectorItem(
                id=row["id"],
                embedding=tuple(emb),
                text=row["question"],
                lang=Lang(row["lang"]),
                meta={"answer": row["answer"], "source_url": row["source_url"], "is_demo": row["is_demo"]},
            )
            for row, emb in zip(rows, embeddings, strict=True)
        ],
    )
    print(f"embedded {len(rows)} faq rows (dim={dim})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
