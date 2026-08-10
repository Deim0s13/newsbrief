#!/usr/bin/env python3
"""
RAG evaluation harness (#262, ADR-0026).

Validates the 4 go/no-go gates defined in ADR-0026 ("Go/No-Go Gates for
Pilot") against whatever data currently exists in ``DATABASE_URL``, now that
the full v0.8.6 RAG milestone (#251-#262, #278-#281) is implemented:

  1. Relatedness precision  - top-5 retrieval finds >=3 related items in
                               >=75% of sampled stories/articles.
  2. Semantic dedupe        - flagged-duplicate rate and effectiveness
                               (#257); reduction without collapsing distinct
                               stories requires a human spot-check of the
                               printed sample.
  3. Historical linking     - >=80% of proposed continuation links judged
                               accurate; this gate requires human review, so
                               the script prints a side-by-side sample for a
                               reviewer rather than a boolean pass/fail.
  4. Latency                - retrieval query latency is acceptable for
                               daily use (uses recorded RetrievalTrace
                               durations; ADR-0026 frames this as "no
                               regression" but there is no legacy retrieval
                               path to regress against, so this gate reports
                               absolute latency against a fixed budget).

Usage:
    python scripts/rag_evaluation.py [--sample-size 50] [--json]

Notes:
- Read-only: never writes to the database.
- Gate 1 and 2 are fully automatic. Gate 3 is printed for human review
  (title-pair + similarity), not auto-scored. Gate 4 is automatic but noted
  as an absolute-latency check rather than a true regression (no prior
  retrieval implementation exists to compare against).
- With a small dataset (e.g. a freshly seeded dev DB) sample sizes will be
  well below the ADR's target of 50; the report flags this explicitly so
  the go/no-go decision isn't overstated from too few samples.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import func  # noqa: E402

from app.db import session_scope  # noqa: E402
from app.orm_models import Item, Story  # noqa: E402
from app.retrieval import RetrievalService  # noqa: E402
from app.retrieval_tracing import get_retrieval_trace_stats  # noqa: E402
from app.semantic_dedup import list_flagged_semantic_duplicates  # noqa: E402

DEFAULT_SAMPLE_SIZE = 50
LATENCY_BUDGET_MS = 500  # generous budget for a single pgvector similarity query

RELATEDNESS_TOP_K = 5
RELATEDNESS_MIN_HITS = 3
RELATEDNESS_PASS_RATE = 0.75
HISTORICAL_LINKING_PASS_RATE = 0.80


@dataclass
class GateResult:
    name: str
    automatic: bool
    sample_size: int
    target_sample_size: int
    metric_value: Optional[float]
    threshold: str
    passed: Optional[bool]  # None when it requires human review
    notes: List[str] = field(default_factory=list)
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gate": self.name,
            "automatic": self.automatic,
            "sample_size": self.sample_size,
            "target_sample_size": self.target_sample_size,
            "metric_value": self.metric_value,
            "threshold": self.threshold,
            "passed": self.passed,
            "notes": self.notes,
            "detail": self.detail,
        }


def evaluate_relatedness_precision(session, sample_size: int) -> GateResult:
    """Gate 1: top-5 retrieval finds >=3 related items in >=75% of cases."""
    story_ids = [
        r[0]
        for r in session.query(Story.id)
        .filter(Story.embedding.isnot(None))
        .order_by(func.random())
        .limit(sample_size)
        .all()
    ]

    service = RetrievalService(session)
    hits = 0
    per_story: List[Dict[str, Any]] = []
    for sid in story_ids:
        results = service.find_related_stories(sid, top_k=RELATEDNESS_TOP_K)
        ok = len(results) >= RELATEDNESS_MIN_HITS
        hits += int(ok)
        per_story.append({"story_id": sid, "related_found": len(results), "ok": ok})

    n = len(story_ids)
    rate = (hits / n) if n else None
    notes = []
    if n < sample_size:
        notes.append(
            f"Only {n} embedded stories available (target {sample_size}); "
            "result should be treated as directional, not conclusive."
        )

    return GateResult(
        name="relatedness_precision",
        automatic=True,
        sample_size=n,
        target_sample_size=sample_size,
        metric_value=round(rate, 4) if rate is not None else None,
        threshold=f">= {RELATEDNESS_PASS_RATE:.0%} of samples find "
        f">= {RELATEDNESS_MIN_HITS} related items in top-{RELATEDNESS_TOP_K}",
        passed=(rate >= RELATEDNESS_PASS_RATE) if rate is not None else None,
        notes=notes,
        detail={"per_story_sample": per_story[:10]},
    )


def evaluate_semantic_dedupe(session, sample_size: int) -> GateResult:
    """Gate 2: dedupe flag rate + a human-reviewable sample of flagged pairs."""
    total_embedded = (
        session.query(func.count(Item.id)).filter(Item.embedding.isnot(None)).scalar()
        or 0
    )
    flagged_count = (
        session.query(func.count(Item.id))
        .filter(Item.duplicate_of_id.isnot(None))
        .scalar()
        or 0
    )
    sample = list_flagged_semantic_duplicates(session, limit=min(sample_size, 20))

    rate = (flagged_count / total_embedded) if total_embedded else None
    notes = [
        "Automatic count only; 'without collapsing distinct stories' requires "
        "a human spot-check of the printed sample pairs below.",
    ]
    if total_embedded == 0:
        notes.append("No embedded articles found; dedupe cannot be evaluated yet.")

    return GateResult(
        name="semantic_dedupe",
        automatic=False,
        sample_size=len(sample),
        target_sample_size=sample_size,
        metric_value=round(rate, 4) if rate is not None else None,
        threshold="Reduction in duplicates without collapsing distinct stories "
        "(qualitative; see sample)",
        passed=None,
        notes=notes,
        detail={
            "total_embedded_articles": total_embedded,
            "flagged_duplicate_count": flagged_count,
            "sample": sample,
        },
    )


def evaluate_historical_linking(session, sample_size: int) -> GateResult:
    """Gate 3: sample proposed continuation links for human review."""
    rows = (
        session.query(Story)
        .filter(Story.continues_story_id.isnot(None))
        .order_by(func.random())
        .limit(sample_size)
        .all()
    )

    sample: List[Dict[str, Any]] = []
    for story in rows:
        prior = session.get(Story, story.continues_story_id)
        sample.append(
            {
                "story_id": story.id,
                "story_title": story.title,
                "continues_story_id": story.continues_story_id,
                "prior_title": prior.title if prior else None,
                "similarity": story.continues_similarity,
            }
        )

    notes = [
        "Requires human judgment; this script cannot auto-score link accuracy.",
        f"Print the sample and have a reviewer mark each as accurate/inaccurate; "
        f"pass requires >= {HISTORICAL_LINKING_PASS_RATE:.0%} judged accurate.",
    ]
    if len(sample) < sample_size:
        notes.append(
            f"Only {len(sample)} continuation links exist (target {sample_size})."
        )

    return GateResult(
        name="historical_linking",
        automatic=False,
        sample_size=len(sample),
        target_sample_size=sample_size,
        metric_value=None,
        threshold=f">= {HISTORICAL_LINKING_PASS_RATE:.0%} of sampled links judged "
        "accurate by human review",
        passed=None,
        notes=notes,
        detail={"sample": sample},
    )


def evaluate_latency(session) -> GateResult:
    """Gate 4: retrieval latency is acceptable for daily use."""
    stats = get_retrieval_trace_stats(session)
    avg_ms = stats.get("avg_duration_ms")

    # Also time a single live call as a sanity check when trace history is thin.
    live_ms = None
    story = session.query(Story).filter(Story.embedding.isnot(None)).limit(1).first()
    if story is not None:
        started = time.monotonic()
        RetrievalService(session).find_related_stories(int(story.id), top_k=5)
        live_ms = round((time.monotonic() - started) * 1000, 1)

    metric = avg_ms if avg_ms is not None else live_ms
    notes = [
        "ADR-0026 frames this as 'no regression', but there is no prior "
        "retrieval implementation to regress against; this checks absolute "
        "latency against a fixed budget instead.",
    ]
    if stats.get("total_traces", 0) == 0:
        notes.append("No RetrievalTrace rows yet; using a single live call instead.")

    return GateResult(
        name="latency",
        automatic=True,
        sample_size=stats.get("sample_size", 0) or (1 if live_ms is not None else 0),
        target_sample_size=DEFAULT_SAMPLE_SIZE,
        metric_value=metric,
        threshold=f"<= {LATENCY_BUDGET_MS}ms average per retrieval query",
        passed=(metric <= LATENCY_BUDGET_MS) if metric is not None else None,
        notes=notes,
        detail={"trace_stats": stats, "live_sample_ms": live_ms},
    )


def run_evaluation(sample_size: int) -> List[GateResult]:
    with session_scope() as session:
        return [
            evaluate_relatedness_precision(session, sample_size),
            evaluate_semantic_dedupe(session, sample_size),
            evaluate_historical_linking(session, sample_size),
            evaluate_latency(session),
        ]


def _format_pass(passed: Optional[bool]) -> str:
    if passed is None:
        return "REVIEW"
    return "PASS" if passed else "FAIL"


def print_report(results: List[GateResult]) -> None:
    print("=" * 72)
    print("RAG Evaluation Report (#262, ADR-0026)")
    print("=" * 72)
    for r in results:
        print(f"\n[{_format_pass(r.passed)}] {r.name}")
        print(f"  threshold : {r.threshold}")
        print(f"  metric    : {r.metric_value}")
        print(f"  sample    : {r.sample_size} (target {r.target_sample_size})")
        for note in r.notes:
            print(f"  note      : {note}")
        if r.name == "semantic_dedupe" and r.detail.get("sample"):
            print("  sample flagged duplicates (review for false collapses):")
            for row in r.detail["sample"][:5]:
                print(
                    f"    item {row['item_id']} ({row['title']!r}) -> "
                    f"duplicate_of {row['duplicate_of_id']} "
                    f"(similarity={row['duplicate_similarity']})"
                )
        if r.name == "historical_linking" and r.detail.get("sample"):
            print("  sample continuation links (review for accuracy):")
            for row in r.detail["sample"][:5]:
                print(
                    f"    story {row['story_id']} ({row['story_title']!r}) "
                    f"continues {row['continues_story_id']} "
                    f"({row['prior_title']!r}), similarity={row['similarity']}"
                )
    print("\n" + "=" * 72)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sample-size",
        type=int,
        default=DEFAULT_SAMPLE_SIZE,
        help=f"Target sample size per gate (default: {DEFAULT_SAMPLE_SIZE})",
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON instead"
    )
    args = parser.parse_args()

    results = run_evaluation(args.sample_size)

    if args.json:
        print(json.dumps([r.to_dict() for r in results], indent=2, default=str))
    else:
        print_report(results)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
