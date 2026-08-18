#!/usr/bin/env python3
"""
Embedding model benchmark for #330.

Compares candidate embedding models against the current production baseline
(``nomic-embed-text``) using a real-data retrieval-precision proxy: articles
that NewsBrief's own clustering/synthesis pipeline already grouped into the
same multi-article story are treated as ground-truth "related" pairs. A good
embedding model should place same-story siblings near each other in vector
space more often than a weaker one.

Methodology:
  1. Sample N items drawn from multi-article stories (>= 2 articles each).
  2. For the baseline, reuse each item's *already-stored* production
     embedding (computed by the live pipeline -- #328) rather than
     re-embedding, since that's exactly what's serving traffic today.
  3. For each candidate model, embed every sampled item's title+summary text
     fresh via Ollama (in-memory only; nothing is persisted to the DB).
  4. For each item, rank all *other* sampled items by cosine similarity and
     check whether at least one same-story sibling appears in the top-K.
  5. Report the sibling-hit rate (the retrieval-precision proxy) and mean
     embedding latency, side by side per model.

Read-only: never writes to the database or to `items`/`stories` embedding
columns. Candidate vectors live only in this process's memory.

Usage:
    python scripts/embedding_benchmark.py [--sample-size 200] [--top-k 5]
    python scripts/embedding_benchmark.py --json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import httpx  # noqa: E402
from sqlalchemy import func  # noqa: E402

from app.db import session_scope  # noqa: E402
from app.embed_backfill import item_embed_text_from_orm  # noqa: E402
from app.orm_models import Item, Story, StoryArticle  # noqa: E402

DEFAULT_SAMPLE_SIZE = 200
DEFAULT_TOP_K = 5
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
BASELINE_MODEL = "nomic-embed-text"
_EMBED_TIMEOUT = 60.0


@dataclass
class ModelResult:
    name: str
    dims: int
    n_embedded: int
    n_skipped_no_text: int
    hit_rate: Optional[float]
    n_eligible: int  # items whose story has >=1 other sampled sibling
    mean_embed_ms: Optional[float]
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "model": self.name,
            "dims": self.dims,
            "n_embedded": self.n_embedded,
            "n_skipped_no_text": self.n_skipped_no_text,
            "n_eligible": self.n_eligible,
            "sibling_hit_rate": (
                round(self.hit_rate, 4) if self.hit_rate is not None else None
            ),
            "mean_embed_ms": (
                round(self.mean_embed_ms, 1) if self.mean_embed_ms is not None else None
            ),
            "notes": self.notes,
        }


def _sample_items(
    session, sample_size: int, max_per_story: int = 4
) -> Tuple[List[Item], Dict[int, int]]:
    """
    Sample items belonging to multi-article stories.

    Returns (items, item_id -> story_id map). Sampling is per-story-first so
    a small sample isn't dominated by a handful of very large stories: pick
    stories with >= 2 articles at random, then take up to `max_per_story`
    articles from each until the sample is full. Pass a `sample_size` >= the
    full multi-article population (and a generous `max_per_story`) to
    benchmark against every eligible article instead of a subsample -- small
    random subsamples (e.g. 200 of ~1200) showed enough run-to-run variance
    to flip which model "won", so prefer the full population when the
    decision matters (#330).
    """
    story_ids = [
        r[0]
        for r in session.query(Story.id)
        .filter(Story.article_count >= 2)
        .order_by(func.random())
        .all()
    ]

    items: List[Item] = []
    item_to_story: Dict[int, int] = {}
    seen_item_ids: set = set()

    for sid in story_ids:
        if len(items) >= sample_size:
            break
        links = (
            session.query(StoryArticle)
            .filter(StoryArticle.story_id == sid)
            .limit(max_per_story)
            .all()
        )
        article_ids = [int(li.article_id) for li in links]
        if not article_ids:
            continue
        rows = session.query(Item).filter(Item.id.in_(article_ids)).all()
        for row in rows:
            if row.id in seen_item_ids:
                continue
            seen_item_ids.add(row.id)
            items.append(row)
            item_to_story[int(row.id)] = int(sid)
        if len(items) >= sample_size:
            break

    return items[:sample_size], item_to_story


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _l2_normalize(vec: List[float]) -> List[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return vec
    return [x / norm for x in vec]


def _truncate_mrl(vec: List[float], dims: int) -> List[float]:
    """MRL (Matryoshka) truncation: take the first `dims` dims, re-normalize."""
    return _l2_normalize(vec[:dims])


def _embed_via_ollama(model: str, text: str) -> Tuple[List[float], float]:
    """Returns (vector, latency_ms). Raises on failure (caller handles)."""
    start = time.monotonic()
    resp = httpx.post(
        f"{OLLAMA_BASE_URL}/api/embeddings",
        json={"model": model, "prompt": text},
        timeout=_EMBED_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    vec = data.get("embedding")
    if not isinstance(vec, list):
        raise ValueError(f"Ollama response missing embedding array for model {model!r}")
    elapsed_ms = (time.monotonic() - start) * 1000.0
    return [float(x) for x in vec], elapsed_ms


def _hit_rate_for_vectors(
    item_ids: List[int],
    vectors: Dict[int, List[float]],
    item_to_story: Dict[int, int],
    top_k: int,
) -> Tuple[Optional[float], int]:
    """
    For each item with a vector, check whether >=1 same-story sibling (that
    also has a vector) appears in the top-K nearest neighbours by cosine
    similarity, restricted to the sampled set. Returns (hit_rate, n_eligible).

    Items whose story has no *other* sampled member with a vector are
    excluded from the denominator (there's nothing correct to retrieve).
    """
    ids_with_vec = [iid for iid in item_ids if iid in vectors]
    hits = 0
    eligible = 0

    for iid in ids_with_vec:
        story_id = item_to_story.get(iid)
        siblings = {
            other
            for other in ids_with_vec
            if other != iid and item_to_story.get(other) == story_id
        }
        if not siblings:
            continue
        eligible += 1

        sims = [
            (other, _cosine(vectors[iid], vectors[other]))
            for other in ids_with_vec
            if other != iid
        ]
        sims.sort(key=lambda t: t[1], reverse=True)
        top_ids = {other for other, _ in sims[:top_k]}
        if top_ids & siblings:
            hits += 1

    rate = (hits / eligible) if eligible else None
    return rate, eligible


def benchmark_baseline(
    items: List[Item], item_to_story: Dict[int, int], top_k: int
) -> ModelResult:
    """Baseline uses each item's already-stored production embedding."""
    vectors: Dict[int, List[float]] = {}
    skipped = 0
    dims = 0
    for item in items:
        vec = item.embedding
        if vec is None:
            skipped += 1
            continue
        vec_list = [float(x) for x in vec]  # type: ignore[attr-defined]
        vectors[int(item.id)] = vec_list
        dims = len(vec_list)

    item_ids = [int(i.id) for i in items]
    rate, eligible = _hit_rate_for_vectors(item_ids, vectors, item_to_story, top_k)
    notes = ["Uses existing stored production embeddings (no re-embedding)."]
    if skipped:
        notes.append(f"{skipped} sampled items had no stored embedding; excluded.")

    return ModelResult(
        name=BASELINE_MODEL,
        dims=dims,
        n_embedded=len(vectors),
        n_skipped_no_text=skipped,
        hit_rate=rate,
        n_eligible=eligible,
        mean_embed_ms=None,
        notes=notes,
    )


def embed_candidate_once(
    model: str,
    items: List[Item],
) -> Tuple[Dict[int, List[float]], List[float], int, int]:
    """
    Embed every item's text with `model` exactly once (native dims).

    Returns (item_id -> vector, latencies_ms, n_skipped_no_text, n_errors).
    Truncated variants are derived from these native vectors by the caller,
    so no duplicate API calls are needed to benchmark MRL truncation.
    """
    vectors: Dict[int, List[float]] = {}
    latencies: List[float] = []
    skipped_no_text = 0
    errors = 0

    for item in items:
        text = item_embed_text_from_orm(item)
        if not text:
            skipped_no_text += 1
            continue
        try:
            vec, latency_ms = _embed_via_ollama(model, text)
        except Exception as e:  # noqa: BLE001 - best-effort benchmark, keep going
            print(f"  [warn] embed failed for item {item.id} ({model}): {e}")
            errors += 1
            continue
        vectors[int(item.id)] = vec
        latencies.append(latency_ms)

    return vectors, latencies, skipped_no_text, errors


def benchmark_candidate(
    model: str,
    items: List[Item],
    item_to_story: Dict[int, int],
    top_k: int,
    native_vectors: Dict[int, List[float]],
    latencies: List[float],
    skipped_no_text: int,
    errors: int,
    *,
    truncate_to: Optional[int] = None,
) -> ModelResult:
    """Compute a ModelResult from vectors already embedded via embed_candidate_once."""
    label = model if truncate_to is None else f"{model} (MRL->{truncate_to}d)"

    if truncate_to is not None:
        vectors = {
            iid: _truncate_mrl(vec, truncate_to) for iid, vec in native_vectors.items()
        }
    else:
        vectors = native_vectors

    dims = len(next(iter(vectors.values()))) if vectors else 0
    item_ids = [int(i.id) for i in items]
    rate, eligible = _hit_rate_for_vectors(item_ids, vectors, item_to_story, top_k)
    mean_ms = (sum(latencies) / len(latencies)) if latencies else None

    notes = []
    if errors:
        notes.append(f"{errors} embed calls failed and were excluded.")
    if truncate_to is not None:
        notes.append("Truncated + L2-renormalized from the native vector (MRL).")

    return ModelResult(
        name=label,
        dims=dims,
        n_embedded=len(vectors),
        n_skipped_no_text=skipped_no_text,
        hit_rate=rate,
        n_eligible=eligible,
        mean_embed_ms=mean_ms,
        notes=notes,
    )


def _print_table(results: List[ModelResult], top_k: int) -> None:
    print()
    print(
        f"Sibling-hit-rate proxy for retrieval precision (top-{top_k}, same-story = ground truth)"
    )
    print("-" * 100)
    header = f"{'Model':<45} {'Dims':>6} {'Embedded':>9} {'Eligible':>9} {'HitRate':>9} {'MeanEmbedMs':>12}"
    print(header)
    print("-" * 100)
    for r in results:
        hit_str = f"{r.hit_rate:.1%}" if r.hit_rate is not None else "n/a"
        ms_str = f"{r.mean_embed_ms:.1f}" if r.mean_embed_ms is not None else "-"
        print(
            f"{r.name:<45} {r.dims:>6} {r.n_embedded:>9} {r.n_eligible:>9} "
            f"{hit_str:>9} {ms_str:>12}"
        )
    print("-" * 100)
    for r in results:
        for note in r.notes:
            print(f"  [{r.name}] {note}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE_SIZE)
    parser.add_argument(
        "--max-per-story",
        type=int,
        default=4,
        help="Cap articles taken per story; raise (e.g. 50) with a large "
        "--sample-size to cover the full multi-article population",
    )
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument(
        "--candidates",
        type=str,
        default="qwen3-embedding:0.6b",
        help="Comma-separated Ollama model names to benchmark against the baseline",
    )
    parser.add_argument(
        "--json", action="store_true", help="Print JSON instead of a table"
    )
    args = parser.parse_args(argv)

    with session_scope() as session:
        items, item_to_story = _sample_items(
            session, args.sample_size, max_per_story=args.max_per_story
        )
        print(
            f"Sampled {len(items)} items from "
            f"{len(set(item_to_story.values()))} multi-article stories",
            file=sys.stderr,
        )

        results: List[ModelResult] = [
            benchmark_baseline(items, item_to_story, args.top_k)
        ]

        for model in [m.strip() for m in args.candidates.split(",") if m.strip()]:
            print(
                f"Embedding sample with {model} ({len(items)} calls)...",
                file=sys.stderr,
            )
            native_vectors, latencies, skipped, errors = embed_candidate_once(
                model, items
            )
            results.append(
                benchmark_candidate(
                    model,
                    items,
                    item_to_story,
                    args.top_k,
                    native_vectors,
                    latencies,
                    skipped,
                    errors,
                )
            )
            native_dims = (
                len(next(iter(native_vectors.values()))) if native_vectors else 0
            )
            if native_dims > 768:
                results.append(
                    benchmark_candidate(
                        model,
                        items,
                        item_to_story,
                        args.top_k,
                        native_vectors,
                        latencies,
                        skipped,
                        errors,
                        truncate_to=768,
                    )
                )

    if args.json:
        print(json.dumps([r.to_dict() for r in results], indent=2))
    else:
        _print_table(results, args.top_k)

    return 0


if __name__ == "__main__":
    sys.exit(main())
