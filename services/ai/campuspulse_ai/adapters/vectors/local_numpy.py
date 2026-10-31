"""LocalNumpyVectorStore: the offline VectorStore (ARCHITECTURE §3.18, P1.7).

The only store build_offline may construct. It holds the frozen collections (`train`,
`injection_exemplars`, `safety_exemplars`) loaded from `models/frozen/vN/index/`, and in tests
any collection a test creates. numpy only: no network, no SDK.

On disk, one directory per collection:
    <index_dir>/<collection>/embeddings.npy   float32, shape (n, dim), row i = items.jsonl line i
    <index_dir>/<collection>/items.jsonl      {"id", "text", "lang", "meta", "active"} per line
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from campuspulse_ai.domain.errors import ArtifactMissing, ArtifactVersionMismatch, NotFound, StoreError
from campuspulse_ai.domain.values import Lang, MetaValue, VectorHit, VectorItem

EMBEDDINGS = "embeddings.npy"
ITEMS = "items.jsonl"
# Filter keys with a fixed meaning; every other key is an equality match on `meta`.
RESERVED_FILTERS = frozenset({"with_embedding", "active", "since", "lang"})


@dataclass
class _Collection:
    dim: int
    ids: list[str] = field(default_factory=list)
    texts: list[str] = field(default_factory=list)
    langs: list[Lang] = field(default_factory=list)
    metas: list[dict[str, MetaValue]] = field(default_factory=list)
    active: list[bool] = field(default_factory=list)
    matrix: np.ndarray = field(init=False)
    index: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.matrix = np.zeros((0, self.dim), dtype=np.float32)


class LocalNumpyVectorStore:
    """VectorStore over in-memory numpy matrices, persisted as .npy + .jsonl per collection.

    - `search`: brute-force cosine, sim descending, ties broken by id. Inactive items are hidden
      unless `filters["active"]` is given. Filters: `active`, `lang`, `since` (meta
      `created_at` >= since), `with_embedding` (fills `VectorHit.embedding`, LD-14), and any other
      key as equality on `meta` (e.g. `building_id`, `category`).
    - `upsert` replaces items by id and creates the collection if needed; `meta["active"]`
      sets the active flag (default True).
    - `count` counts the items `search` could return under the same filters.

    Errors: StoreError for an unknown collection, a wrong-length vector, or any write to a
    read-only store; NotFound from `set_active` on a missing id; `load` raises ArtifactMissing
    for missing files and ArtifactVersionMismatch when the stored dim differs from `expected_dim`.
    """

    def __init__(self, dim: int, *, read_only: bool = False, collections: Iterable[str] = ()) -> None:
        self.dim = dim
        self.read_only = read_only
        self._collections: dict[str, _Collection] = {name: _Collection(dim) for name in collections}

    @classmethod
    def load(cls, index_dir: Path, *, expected_dim: int, read_only: bool = True) -> LocalNumpyVectorStore:
        """Load every collection directory under `index_dir` (read-only by default)."""
        index_dir = Path(index_dir)
        if not index_dir.is_dir():
            raise ArtifactMissing(f"vector index directory not found: {index_dir}")
        store = cls(expected_dim)
        for coll_dir in sorted(p for p in index_dir.iterdir() if p.is_dir()):
            emb_path, items_path = coll_dir / EMBEDDINGS, coll_dir / ITEMS
            for path in (emb_path, items_path):
                if not path.is_file():
                    raise ArtifactMissing(f"vector collection file missing: {path}")
            matrix = np.load(emb_path, allow_pickle=False)
            if matrix.ndim != 2 or matrix.shape[1] != expected_dim:
                raise ArtifactVersionMismatch(
                    f"{coll_dir.name}: stored vectors have shape {matrix.shape}, expected dim {expected_dim}"
                )
            lines = [json.loads(line) for line in items_path.read_text(encoding="utf-8").splitlines() if line]
            if len(lines) != matrix.shape[0]:
                raise ArtifactVersionMismatch(
                    f"{coll_dir.name}: {matrix.shape[0]} vectors but {len(lines)} items"
                )
            coll = _Collection(expected_dim)
            for row in lines:
                _append(coll, row["id"], row["text"], Lang(row["lang"]), row.get("meta") or {}, row["active"])
            coll.matrix = matrix.astype(np.float32, copy=False)
            store._collections[coll_dir.name] = coll
        store.read_only = read_only
        return store

    def save(self, index_dir: Path) -> list[Path]:
        """Write every collection under `index_dir`; returns the files written."""
        written: list[Path] = []
        for name, coll in sorted(self._collections.items()):
            coll_dir = Path(index_dir) / name
            coll_dir.mkdir(parents=True, exist_ok=True)
            np.save(coll_dir / EMBEDDINGS, coll.matrix.astype(np.float32), allow_pickle=False)
            lines = (
                json.dumps(
                    {"id": i, "text": t, "lang": str(lang), "meta": meta, "active": act},
                    ensure_ascii=False,
                    sort_keys=True,
                )
                for i, t, lang, meta, act in zip(
                    coll.ids, coll.texts, coll.langs, coll.metas, coll.active, strict=True
                )
            )
            # LF on every OS: the file is hashed into MANIFEST.json and git stores it with LF (.gitattributes)
            body = "".join(f"{line}\n" for line in lines)
            (coll_dir / ITEMS).write_text(body, encoding="utf-8", newline="\n")
            written += [coll_dir / EMBEDDINGS, coll_dir / ITEMS]
        return written

    def collections(self) -> frozenset[str]:
        return frozenset(self._collections)

    def upsert(self, collection: str, items: Sequence[VectorItem]) -> None:
        self._writable()
        coll = self._collections.setdefault(collection, _Collection(self.dim))
        new_rows: list[np.ndarray] = []
        for item in items:
            vec = self._vector(item.embedding)
            meta = {k: v for k, v in item.meta.items() if k != "active"}
            active = bool(item.meta.get("active", True))
            if item.id in coll.index:
                i = coll.index[item.id]
                coll.texts[i], coll.langs[i], coll.metas[i], coll.active[i] = (
                    item.text,
                    item.lang,
                    meta,
                    active,
                )
                coll.matrix[i] = vec
            else:
                _append(coll, item.id, item.text, item.lang, meta, active)
                new_rows.append(vec)
        if new_rows:
            coll.matrix = np.vstack([coll.matrix, np.stack(new_rows)])

    def search(
        self,
        collection: str,
        query: Sequence[float],
        k: int,
        min_sim: float = 0.0,
        filters: Mapping[str, object] | None = None,
    ) -> list[VectorHit]:
        coll = self._get(collection)
        q = self._vector(query)
        f = dict(filters or {})
        rows = self._matching(coll, f)
        if k <= 0 or not rows:
            return []
        sub = coll.matrix[rows]
        norms = np.linalg.norm(sub, axis=1) * float(np.linalg.norm(q))
        with np.errstate(divide="ignore", invalid="ignore"):
            sims = np.where(norms > 0, (sub @ q) / norms, 0.0)
        scored = sorted(
            ((float(s), coll.ids[r], r) for s, r in zip(sims, rows, strict=True) if s >= min_sim),
            key=lambda t: (-t[0], t[1]),
        )[:k]
        with_embedding = bool(f.get("with_embedding"))
        return [
            VectorHit(
                id=id,
                text=coll.texts[r],
                sim=sim,
                lang=coll.langs[r],
                meta=dict(coll.metas[r]),
                embedding=tuple(float(x) for x in coll.matrix[r]) if with_embedding else None,
            )
            for sim, id, r in scored
        ]

    def set_active(self, collection: str, id: str, active: bool) -> None:
        self._writable()
        coll = self._collections.get(collection)
        if coll is None or id not in coll.index:
            raise NotFound(f"{collection} item {id} not found")
        coll.active[coll.index[id]] = active

    def count(self, collection: str, filters: Mapping[str, object] | None = None) -> int:
        return len(self._matching(self._get(collection), dict(filters or {})))

    def _matching(self, coll: _Collection, f: Mapping[str, object]) -> list[int]:
        want_active = bool(f["active"]) if f.get("active") is not None else True
        lang = f.get("lang")
        since = f.get("since")
        since_iso = since.isoformat() if isinstance(since, datetime) else since
        meta_eq = {k: v for k, v in f.items() if k not in RESERVED_FILTERS and v is not None}
        rows = []
        for i in range(len(coll.ids)):
            meta = coll.metas[i]
            if coll.active[i] != want_active:
                continue
            if lang is not None and str(coll.langs[i]) != str(lang):
                continue
            if since_iso is not None and _iso_utc(meta.get("created_at")) < _iso_utc(since_iso):
                continue
            if any(meta.get(key) != value for key, value in meta_eq.items()):
                continue
            rows.append(i)
        return rows

    def _get(self, collection: str) -> _Collection:
        try:
            return self._collections[collection]
        except KeyError:
            raise StoreError(f"unknown vector collection {collection!r}") from None

    def _vector(self, values: Sequence[float]) -> np.ndarray:
        vec = np.asarray(values, dtype=np.float32)
        if vec.shape != (self.dim,):
            raise StoreError(f"vector has shape {vec.shape}, the store expects ({self.dim},)")
        return vec

    def _writable(self) -> None:
        if self.read_only:
            raise StoreError("this LocalNumpyVectorStore is read-only (frozen artifacts)")


def _append(
    coll: _Collection, id: str, text: str, lang: Lang, meta: Mapping[str, MetaValue], active: bool
) -> None:
    coll.index[id] = len(coll.ids)
    coll.ids.append(id)
    coll.texts.append(text)
    coll.langs.append(lang)
    coll.metas.append(dict(meta))
    coll.active.append(active)


def _iso_utc(value: object) -> datetime:
    """Parse an ISO timestamp for comparison (naive = UTC); a missing one sorts first."""
    if value is None:
        return datetime.min.replace(tzinfo=UTC)
    parsed = datetime.fromisoformat(str(value))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
