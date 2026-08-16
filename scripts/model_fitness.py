#!/usr/bin/env python3
"""
Model-fitness evaluation harness (#341).

Formalizes the ad hoc script written during #336 (macOS oMLX model
selection) into permanent dev tooling. Runs one or more candidate LLM
models against NewsBrief's real synthesis and entity-extraction prompts
(the actual prompt builders in `app/prompts/synthesis.py` and
`app/entities.py`), validates output through the real `app/llm_output.py`
parser (including its multi-strategy JSON extraction and repair logic),
and reports timing + JSON quality per candidate.

This is what caught a real, silent failure mode during #336: a candidate
that only registered "parse OK" via regex-repair, not a clean model output
-- a generic benchmark or toy prompt would have missed it. Model swaps on
any platform (#332 Windows, #330 embeddings, future re-evaluations) should
use this rather than a one-off throwaway script.

Usage:
    # Ollama backend (Windows default; also works on macOS/Linux)
    python scripts/model_fitness.py --backend ollama --model llama3.1:8b
    python scripts/model_fitness.py --backend ollama \\
        --model llama3.1:8b --model qwen3:14b --model deepseek-r1:14b

    # oMLX backend (macOS)
    python scripts/model_fitness.py --backend mlx \\
        --model lmstudio-community--Qwen3-30B-A3B-Instruct-2507-MLX-4bit

    # Test chain-of-thought mode (mirrors stories.py's deep-synthesis path, #286)
    python scripts/model_fitness.py --backend ollama --model deepseek-r1:14b --think

    # JSON output for scripting/comparison
    python scripts/model_fitness.py --backend ollama --model qwen3:14b --json

Notes:
- Read-only: never touches the database. DATABASE_URL still must be set in
  the environment though -- `app.entities`/`app.llm` import `app.db` at
  module level (unconditionally requires it, ADR-0022), so it needs to be
  set even though this script issues no queries.
  Do NOT `source .env` for this -- that file holds container-facing values
  (`db:5432`, `host.containers.internal`) that only resolve *inside*
  Podman, and sourcing it will also clobber OLLAMA_BASE_URL and break
  connectivity to a host-native Ollama. Instead export the dev-DB URL
  directly, e.g.:
    export DATABASE_URL="postgresql://newsbrief:newsbrief_dev@localhost:5433/newsbrief"
  and leave OLLAMA_BASE_URL unset so it defaults to localhost:11434.
- `--think` defaults to False, matching the #332 default in
  `OllamaBackend.generate()` -- pass it to explicitly test a model's
  chain-of-thought output instead of the fast direct-answer path.
- oMLX candidates must already be loaded/discoverable on the target oMLX
  instance (`OMLX_BASE_URL`/`OMLX_API_KEY` env vars) -- this script does not
  pull/download models for either backend; use `ollama pull <model>` first.
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

try:
    from app.entities import _create_entity_extraction_prompt  # noqa: E402
    from app.llm import OLLAMA_BASE_URL  # noqa: E402
    from app.llm_backends import get_backend  # noqa: E402
    from app.llm_output import (  # noqa: E402
        EnhancedEntityOutput,
        SynthesisOutput,
        parse_and_validate,
    )
    from app.prompts import AnalysisResult, StoryType  # noqa: E402
    from app.prompts.synthesis import get_synthesis_prompt  # noqa: E402
except RuntimeError as e:
    if "DATABASE_URL" in str(e):
        print(
            "ERROR: DATABASE_URL is not set.\n\n"
            "This script never queries the database, but app.entities and "
            "app.llm import app.db at module level (unconditional, "
            "ADR-0022), so DATABASE_URL must still be set for the import "
            "to succeed.\n\n"
            "Do NOT `source .env` for this -- it holds container-facing "
            "values (db:5432, host.containers.internal) that break "
            "host-native Ollama connectivity too. Instead:\n"
            '  export DATABASE_URL="postgresql://newsbrief:newsbrief_dev@localhost:5433/newsbrief"\n'
            "  python scripts/model_fitness.py ...",
            file=sys.stderr,
        )
        sys.exit(1)
    raise

# ---------------------------------------------------------------------------
# Representative fixture data -- same shape as real pipeline inputs, not a
# toy prompt. Domain matches NewsBrief's typical content (tech/AI news) so
# candidate models see prompts structurally identical to production.
# ---------------------------------------------------------------------------

_FIXTURE_ARTICLE_SUMMARIES: List[Dict[str, str]] = [
    {
        "title": "Cloud provider unveils new AI inference chip for enterprise customers",
        "summary": (
            "A major cloud provider announced a custom silicon chip optimized "
            "for large language model inference, claiming 3x throughput "
            "improvements over prior-generation GPUs at lower cost per token. "
            "The chip will be available in preview to select enterprise "
            "customers starting next quarter, with general availability "
            "planned for later in the year."
        ),
    },
    {
        "title": "Rival cloud vendor responds with price cuts on GPU instances",
        "summary": (
            "Following the chip announcement, a competing cloud vendor cut "
            "prices on its own GPU-backed inference instances by up to 20%, "
            "in what analysts describe as an early skirmish in a broader "
            "price war over AI infrastructure. The vendor also hinted at its "
            "own custom silicon roadmap without providing further detail."
        ),
    },
    {
        "title": "Enterprise AI spending expected to double amid infrastructure race",
        "summary": (
            "A new industry report projects enterprise spending on AI "
            "inference infrastructure will double within two years, driven "
            "by growing production deployment of large language models "
            "rather than experimentation. The report names custom silicon, "
            "not just raw GPU capacity, as the key differentiator going "
            "forward for cost-sensitive enterprise buyers."
        ),
    },
]

_FIXTURE_ANALYSIS = AnalysisResult(
    timeline=[
        "Cloud provider announces custom AI inference chip",
        "Rival vendor cuts GPU instance prices in response",
        "Industry report projects doubling of enterprise AI infrastructure spend",
    ],
    core_facts=[
        "A major cloud provider has built its own AI inference silicon",
        "A competitor responded with price cuts rather than a chip of its own yet",
        "Enterprise AI infrastructure spending is shifting from experimentation to production",
    ],
    tensions=[
        "Whether custom silicon or price competition will define the market",
    ],
    key_players=[
        "The cloud provider announcing the chip",
        "The rival cloud vendor cutting prices",
    ],
    gaps=[
        "No independent benchmarks of the new chip's real-world performance yet",
    ],
    narrative_thread="Cloud providers are racing to control AI inference costs through custom silicon and pricing.",
)

_FIXTURE_ENTITY_ARTICLE = _FIXTURE_ARTICLE_SUMMARIES[0]


@dataclass
class TaskResult:
    task: str
    parse_ok: bool
    duration_s: float
    strategy: str
    repairs: List[str] = field(default_factory=list)
    error: Optional[str] = None
    tokens_generated: Optional[int] = None
    raw_preview: str = ""


@dataclass
class CandidateResult:
    model: str
    backend: str
    tasks: List[TaskResult] = field(default_factory=list)

    @property
    def total_duration_s(self) -> float:
        return sum(t.duration_s for t in self.tasks)

    @property
    def all_parsed_ok(self) -> bool:
        return all(t.parse_ok for t in self.tasks)


def _extract_tokens_generated(raw_response: Dict[str, Any]) -> Optional[int]:
    """Best-effort token count across backend response shapes."""
    if "eval_count" in raw_response:  # Ollama native /api/generate
        return raw_response.get("eval_count")
    raw = raw_response.get("raw") or {}
    usage = raw.get("usage") or {}  # oMLX OpenAI-compatible /v1/completions
    return usage.get("completion_tokens")


def _run_task(
    backend: Any,
    model: str,
    task_name: str,
    prompt: str,
    model_class: type,
    think: bool,
    max_tokens: int,
) -> TaskResult:
    options = {
        "temperature": 0.3,
        "top_k": 40,
        "top_p": 0.9,
        "num_predict": max_tokens,
    }
    kwargs: Dict[str, Any] = {"think": think} if think else {}

    start = time.monotonic()
    try:
        response = backend.generate(
            model=model, prompt=prompt, options=options, **kwargs
        )
    except Exception as e:
        return TaskResult(
            task=task_name,
            parse_ok=False,
            duration_s=time.monotonic() - start,
            strategy="n/a",
            error=f"generate() raised: {e}",
        )
    duration = time.monotonic() - start

    raw_text = response.get("response", "")
    parsed, metrics = parse_and_validate(raw_text, model_class)

    return TaskResult(
        task=task_name,
        parse_ok=parsed is not None,
        duration_s=duration,
        strategy=metrics.strategy_used,
        repairs=metrics.repairs_made,
        error=metrics.error_message if parsed is None else None,
        tokens_generated=_extract_tokens_generated(response),
        raw_preview=raw_text[:200],
    )


def run_candidate(
    backend: Any,
    model: str,
    backend_type: str,
    think: bool,
    max_tokens: int,
    verbose: bool,
) -> CandidateResult:
    result = CandidateResult(model=model, backend=backend_type)

    synthesis_prompt = get_synthesis_prompt(
        StoryType.EVOLVING, _FIXTURE_ANALYSIS, _FIXTURE_ARTICLE_SUMMARIES
    )
    entity_prompt = _create_entity_extraction_prompt(
        _FIXTURE_ENTITY_ARTICLE["title"],
        _FIXTURE_ENTITY_ARTICLE["summary"],
        enhanced=True,
    )

    for task_name, prompt, model_class in (
        ("synthesis", synthesis_prompt, SynthesisOutput),
        ("entities", entity_prompt, EnhancedEntityOutput),
    ):
        task_result = _run_task(
            backend, model, task_name, prompt, model_class, think, max_tokens
        )
        result.tasks.append(task_result)
        if verbose:
            status = "PARSE_OK" if task_result.parse_ok else "PARSE_FAIL"
            print(
                f"  [{model}] {task_name}: {status} in {task_result.duration_s:.1f}s "
                f"strategy={task_result.strategy} repairs={task_result.repairs}"
            )
            if task_result.error:
                print(f"    error: {task_result.error}")
            print(f"    raw: {task_result.raw_preview!r}")

    return result


def print_comparison_table(results: List[CandidateResult]) -> None:
    print("\n" + "=" * 100)
    print("MODEL FITNESS COMPARISON")
    print("=" * 100)
    header = f"{'Model':<55} {'Backend':<8} {'Synth':<12} {'Entities':<12} {'Total':<10} {'JSON quality'}"
    print(header)
    print("-" * 100)
    for r in results:
        by_task = {t.task: t for t in r.tasks}
        synth = by_task.get("synthesis")
        ents = by_task.get("entities")
        synth_str = f"{synth.duration_s:.1f}s" if synth else "n/a"
        ents_str = f"{ents.duration_s:.1f}s" if ents else "n/a"
        quality = (
            "clean"
            if r.all_parsed_ok and not any(t.repairs for t in r.tasks)
            else ("repaired" if r.all_parsed_ok else "FAILED")
        )
        print(
            f"{r.model:<55} {r.backend:<8} {synth_str:<12} {ents_str:<12} "
            f"{r.total_duration_s:<10.1f} {quality}"
        )
    print("=" * 100)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run candidate LLM models through NewsBrief's real prompts + parser.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--backend",
        required=True,
        choices=["ollama", "mlx"],
        help="Backend to test against (ollama or mlx/oMLX)",
    )
    parser.add_argument(
        "--model",
        required=True,
        action="append",
        dest="models",
        help="Model tag/ID to test (repeatable to compare several)",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Override backend base URL (defaults to OLLAMA_BASE_URL / OMLX_BASE_URL)",
    )
    parser.add_argument(
        "--think",
        action="store_true",
        help="Enable chain-of-thought mode (mirrors stories.py's deep-synthesis path)",
    )
    parser.add_argument(
        "--max-tokens", type=int, default=800, help="num_predict / max_tokens per call"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of a table",
    )
    args = parser.parse_args()

    base_url = args.base_url or (OLLAMA_BASE_URL if args.backend == "ollama" else None)
    backend = get_backend(base_url or OLLAMA_BASE_URL, backend_type=args.backend)

    if not backend.is_available():
        print(
            f"ERROR: {args.backend} backend not reachable at "
            f"{getattr(backend, 'base_url', '?')}",
            file=sys.stderr,
        )
        return 1

    results = []
    for model in args.models:
        print(f"\nTesting {model} ({args.backend})...")
        results.append(
            run_candidate(
                backend, model, args.backend, args.think, args.max_tokens, verbose=True
            )
        )

    if args.json:
        print(
            json.dumps(
                [
                    {
                        "model": r.model,
                        "backend": r.backend,
                        "total_duration_s": r.total_duration_s,
                        "all_parsed_ok": r.all_parsed_ok,
                        "tasks": [
                            {
                                "task": t.task,
                                "parse_ok": t.parse_ok,
                                "duration_s": t.duration_s,
                                "strategy": t.strategy,
                                "repairs": t.repairs,
                                "tokens_generated": t.tokens_generated,
                                "error": t.error,
                            }
                            for t in r.tasks
                        ],
                    }
                    for r in results
                ],
                indent=2,
            )
        )
    else:
        print_comparison_table(results)

    return 0 if all(r.all_parsed_ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
