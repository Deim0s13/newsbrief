# ADR-0033: Hardware-Informed Model Selection

## Status
**Accepted** — June 2026

## Context

ADR-0025 established the three-profile model strategy (fast / balanced / quality) with Qwen 2.5 variants as the primary model family, validated against a single machine (MacBook Pro M4, 48 GB unified memory). ADR-0032 formalised the two-machine deployment reality: a macOS MBP and a Windows laptop, each with meaningfully different hardware.

No hardware analysis had been performed against the **Windows laptop** to verify whether the chosen models were appropriate for its constraints, and the macOS models had not been revisited since the M4 evaluation. The result was a single set of model profiles applied uniformly to both hosts, despite one having 48 GB unified memory (macOS M4 Pro) and the other having a discrete 16 GB VRAM GPU (Windows RTX 4090 Laptop).

### LLMfit Analysis

LLMfit (container `ghcr.io/alexsjones/llmfit`) was run on both hosts to evaluate hardware fit, estimated throughput, and recommended models. Live Ollama benchmarks (`llmfit bench`) were also run on Windows to capture real inference tok/s.

**Reports saved to:** OneDrive Desktop — `report.html` (macOS), `report-windows.html` (Windows)

### Key Findings

**Windows (RTX 4090 Laptop, 16 GB VRAM, 32 GB RAM, i9-13980HX):**

| Model           | Fit      | VRAM Used | Actual tok/s | LLMfit Score |
|-----------------|----------|-----------|--------------|--------------|
| mistral:7b      | Perfect  | 9.1 GB    | 98.3         | 78.8         |
| llama3.1:8b     | Perfect  | 9.9 GB    | 92.1         | 79.4         |
| qwen2.5:14b     | Perfect  | 13.8 GB   | 50.5         | 68.5         |
| qwen3:14b       | Perfect  | 13.6 GB   | 49.7         | 72.2         |
| deepseek-r1:14b | Perfect  | 13.8 GB   | 51.2         | 84.9         |
| qwen2.5:32b     | Marginal | 14.6 GB   | not installed | 59.0        |

`qwen2.5:32b` requires a minimum of 16.8 GB VRAM at Q4_K_M; with only 16 GB available it can only run at Q2_K (the lossiest available quantisation), giving a score of 59.0 — the lowest of any installed model. It is not viable as the quality profile on this hardware.

**macOS (M4 Pro, 48 GB unified memory):**

Unified memory means VRAM and RAM are shared. Models up to ~30 GB fit comfortably. The MoE architecture of Qwen3.6-35B-A3B (active parameters ~3B, total 36B) loads all experts in unified memory and is Perfect fit through 128K context. Model tags on macOS to be confirmed during implementation (Issue #318).

**Correction (August 2026):** the hardware description above (M3 Pro, 36 GB) was inaccurate — this ADR's own June 2026 acceptance was already validated against the M4 Pro / 48 GB machine referenced in ADR-0025's Context section, not a separate M3 Pro. No LLMfit re-run was needed for this correction; see the [addendum](#addendum-august-2026-omlx-adoption-on-macos) below for the actual macOS re-evaluation this session (which used the correct M4 Pro / 48 GB spec throughout).

---

## Decision

### 1. Add `device_profiles` to `model_config.json`

Introduce a `device_profiles` top-level block (config version bumped to `"2.1"`) mapping platform key → profile name → Ollama model tag:

```json
"device_profiles": {
  "windows": {
    "fast":     "llama3.1:8b",
    "balanced": "qwen3:14b",
    "quality":  "deepseek-r1:14b"
  },
  "darwin": {
    "fast":     "qwen3:4b",
    "balanced": "qwen3:14b",
    "quality":  "qwen3.6:35b"
  }
}
```

macOS model tags are subject to confirmation during Issue #331 (MBP verification). If `qwen3.6:35b` is not available as an Ollama tag, `qwen3:14b` serves as the quality fallback on macOS.

**Update (2026-08-11):** all three macOS tags (`qwen3:4b`, `qwen3:14b`, `qwen3.6:35b`) and the Windows tags were confirmed to exist on the Ollama registry. Live pull/benchmark verification is tracked in #331 (macOS) and #332 (Windows) — the latter also covers a newly identified risk: `deepseek-r1:14b` emits `<think>...</think>` reasoning blocks by default, which `app/llm_output.py` does not currently handle before JSON parsing.

### 2. Model assignments

| Platform | Profile  | Previous model  | New model           |
|----------|----------|-----------------|---------------------|
| Windows  | fast     | mistral:7b      | llama3.1:8b         |
| Windows  | balanced | qwen2.5:14b     | qwen3:14b           |
| Windows  | quality  | qwen2.5:32b     | deepseek-r1:14b     |
| macOS    | fast     | mistral:7b      | qwen3:4b (TBC)      |
| macOS    | balanced | qwen2.5:14b     | qwen3:14b           |
| macOS    | quality  | qwen2.5:32b     | qwen3.6:35b (TBC)   |

Rationale per Windows change:
- **fast:** `llama3.1:8b` outscores `mistral:7b` (79.4 vs 78.8), with better quality (83 vs 76) and 1M token context vs 32K at comparable speed (92 vs 98 tok/s).
- **balanced:** `qwen3:14b` is a newer generation than `qwen2.5:14b`, scores higher (72.2 vs 68.5), and fits the same VRAM footprint.
- **quality:** `deepseek-r1:14b` is the highest-scoring installed model (84.9) and fits comfortably in 16 GB VRAM. `qwen2.5:32b` is physically marginal and only viable at Q2_K.

### 3. Device-aware model resolution in `SettingsService`

`SettingsService.get_active_model()` (`app/settings.py`) is extended with an additional resolution step:

1. `model_override` from `settings.json` — highest precedence, unchanged
2. `device_profiles[platform_key][active_profile]` from `model_config.json` — **new**
3. `profiles[active_profile].model` from `model_config.json` — existing generic fallback
4. `NEWSBRIEF_LLM_MODEL` env var / hardcoded default

Platform key is derived from `sys.platform` (`win32` → `windows`, `darwin` → `darwin`, else `linux`), overridable via `NEWSBRIEF_DEVICE_TYPE` env var for container deployments.

### 4. Re-run cadence

LLMfit analysis should be re-run when hardware changes meaningfully (new GPU, VRAM upgrade, new host added). Reports should be saved alongside prior reports on OneDrive Desktop for comparison.

---

## Consequences

### Positive

- The correct model for each host is selected automatically without any manual configuration after initial profile assignment
- `qwen2.5:32b` is retired from the quality slot where it was marginal — output quality improves on Windows
- `deepseek-r1:14b` as the Windows quality model brings chain-of-thought reasoning to complex multi-source stories
- The user-facing profile concept (fast / balanced / quality) is unchanged; device awareness is transparent
- Hardware analysis is now documented and reproducible

### Negative

- Two sets of model assignments to maintain; adding a third machine requires a new `device_profiles` entry and LLMfit analysis
- macOS model tags must be verified and pulled before the darwin block is live (Issue #318)
- `deepseek-r1:14b` has a higher time-to-first-token (~1.5 s) due to chain-of-thought generation; this is a latency tradeoff for the quality profile
- LLMfit estimates diverge from real Ollama CUDA performance (estimates run ~3× low on Windows); re-analysis after hardware changes should include live benchmark runs

---

## Related ADRs

- [ADR-0025: LLM Model Selection and Profile Strategy](0025-llm-model-selection.md)
- [ADR-0032: Cross-Platform Continuous Delivery Strategy](0032-cross-platform-cd-strategy.md)

## References

- GitHub milestone: [v0.8.7 — Model Optimisation & Platform Intelligence](https://github.com/Deim0s13/newsbrief/milestone/46)
- Issue #315 — Write ADR-0033 (closed — this document)
- Issue #316 — Add model specs to model_config.json
- Issue #317 — Add device_profiles block
- Issue #319 — Implement device-aware model resolution in SettingsService
- Issue #320 — Surface effective model in /config UI
- Issue #321 — Unit tests for device-aware model resolution
- Issue #322 — Update MODEL-PROFILES.md and ARCHITECTURE.md
- Issue #329 — Verify Ollama's native MLX backend on macOS
- Issue #331 — Verify macOS candidate model tags
- Issue #332 — Validate Windows model swap (incl. deepseek-r1 thinking-block risk) (closed — see [Windows Live Validation addendum](#addendum-august-2026-windows-live-validation-332) below)
- Issue #330 — Re-evaluate embedding model for item/story embeddings (closed — see [Embedding Model Re-evaluation addendum](#addendum-august-2026-embedding-model-re-evaluation-330) below)
- Issue #341 — Formalize the model-fitness harness (`scripts/model_fitness.py`), used for this validation

---

## Addendum (August 2026): oMLX Adoption on macOS

**Status: GO — adopted.** This addendum documents the evaluation and evidence behind switching the macOS backend from Ollama to [oMLX](https://github.com/omlx-org/omlx) (a standalone MLX-based inference server with an OpenAI-compatible API), which is the piece of "Issue #329 — Verify Ollama's native MLX backend on macOS" this ADR originally deferred. Windows is unaffected — it stays on Ollama with the `deepseek-r1:14b`/`qwen3:14b`/`llama3.1:8b` assignments above.

### Trigger

A real end-to-end story-generation run on the M4 Pro macOS host (753 backlog articles clustering into 227 groups, `qwen2.5:14b` balanced profile via Ollama) took **~3h19m wall-clock**, confirmed by profiling to be **99.98% LLM call time** (DB writes were ~16 seconds of the total). This is the exact condition ADR-0025's Risks table flagged as the trigger to revisit MLX ("Ollama performance becomes bottleneck → MLX migration path documented; can revisit if needed").

### Ruling out the obvious hypothesis first

Before concluding raw model throughput was the bottleneck, "is `max_workers=3` in `app/stories.py` actually running in parallel, or is Ollama serialising requests via `OLLAMA_NUM_PARALLEL`?" was tested directly — same model, same host, single call vs. 3-concurrent:

| Backend / Model | Single call | 3 concurrent (total) | Notes |
|---|---|---|---|
| Ollama, `qwen2.5:14b` (then-current baseline) | 31.4s | 37.9s | Real concurrency confirmed — not a serialization bug |
| MLX (`mlx_lm.server`), `qwen2.5:14b`-4bit (same model, different runtime) | 16.1s | 13.8s | ~2x faster single-call; concurrent batch adds almost no extra cost |
| MLX, `Qwen3-30B-A3B` (MoE) | 15.7s | 7.5s | **5x faster than Ollama** on the exact 3-concurrent pattern the pipeline uses |

Ollama's own concurrency was genuine (1.20x total time for 3 concurrent vs. single, i.e. real parallel scheduling — not the ~3x a naive serialization bug would show). This ruled out a quick fix and confirmed the bottleneck was raw per-call throughput plus runtime overhead, making the MLX/oMLX comparison the right next step rather than a distraction.

### Newsbrief-specific model-fitness methodology

Rather than trusting borrowed model picks from other projects (`ai-lab`) or generic leaderboards, each macOS profile candidate was run through Newsbrief's **actual** synthesis and entity-extraction prompts, parsed with the **actual** `app/llm_output.py` validator (including its repair/circuit-breaker logic), and cross-checked against `llmfit` (an independent hardware-fit scoring tool) as a second signal — not a replacement for the task-specific test.

**Baseline (Ollama, current production model):**

| Candidate | Synthesis | Entities | Total | JSON quality |
|---|---|---|---|---|
| Ollama `qwen2.5:14b` | 21.4s | 16.8s | 38.2s | Clean, direct parse |

**Rejected candidates** (surfaced real, silent failure modes newer-generation models don't automatically avoid):

| Candidate | Total | Result |
|---|---|---|
| oMLX `Qwen3.5-9B` | 148.9s (3.9x **slower**) | Needed JSON repair on both calls; one "parse OK" was only salvaged via regex extraction, not a clean model output |
| oMLX `Qwen3.5-35B-A3B` (unquantized bf16) | — | 507 Insufficient Storage — exceeded available memory alongside other resident models |

**Final validated candidates, all three profile tiers, via oMLX:**

| Tier | Candidate | Total time | JSON quality | llmfit corroboration |
|---|---|---|---|---|
| fast | `Llama-3.2-3B-Instruct-4bit` | 24.6s | Parse OK, minor repair needed | Top "Chat" category score (87.4), ~100 tok/s estimated |
| balanced | `Qwen3-30B-A3B-Instruct-2507` (MoE, ~3B active/30B total params) | 26.5s | Parse OK, **clean, no repair** — best result of all candidates tested | Tied top "Chat" category score (87.4), ~94 tok/s estimated |
| quality | `Qwen3.6-35B-A3B` (unsloth dynamic quant, MoE) | 35.3s | Parse OK, minor repair needed | "Perfect fit" (score 74.7 base model / 77.3 for the actually-deployed MLX-4bit build) |

All three beat the Ollama baseline (38.2s) individually on a single call, and the earlier concurrency test showed the gap widens sharply (up to 5x) under the pipeline's real 3-concurrent workload pattern.

### End-to-end validation (#339)

A full production run using the balanced-tier oMLX model against the real backlog (753 articles, 113 clusters, 14-day window) completed in **24.9 minutes**, directly comparable to the ~3h+ Ollama baseline for a similarly-sized batch — an order-of-magnitude improvement, consistent with the per-call and concurrency benchmarks above. 89 of 113 clusters (~79%) synthesized successfully; the remaining ~21% hit a distinct bug (`'NoneType' object has no attribute 'strip'`) tracked separately in [#340](https://github.com/Deim0s13/newsbrief/issues/340) — not a backend-fitness issue, and not blocking this go/no-go decision.

A blocking schema bug was found and fixed during this run: `stories.model`/`synthesis_cache.model`/`llm_metrics.model` were `VARCHAR(50)`, sized for short Ollama tags (`qwen2.5:14b`), but oMLX model IDs are much longer (e.g. `lmstudio-community--Qwen3-30B-A3B-Instruct-2507-MLX-4bit`, 56 chars) — every insert failed silently until this was caught. Fixed via migration `028_widen_model_columns.py` (widened to `Text`, matching the existing convention for `items.ai_model` etc.).

### Decision

**Go.** macOS switches to oMLX as its default backend (`device_profiles.darwin.backend = "mlx"`), implemented via the pluggable backend abstraction in `app/llm_backends.py` (#335/#336/#337). Windows is unaffected. See ADR-0025's amendment for how this changes that ADR's original "Ollama only" recommendation.

### Operational notes carried into implementation

- oMLX has no pull-on-demand — new models need a full oMLX restart to be discovered, unlike Ollama's on-demand pull. Handled with clear errors rather than mid-run 404s.
- oMLX binds to loopback by default; container reachability via `host.containers.internal` needed verification before this could proceed (#334) — confirmed reachable.
- Shared oMLX instance with the separate `ai-lab` project: memory headroom is workable (largest three Newsbrief models ≈ 35GB against ~37-42GB available) but relies on oMLX's LRU eviction under simultaneous load rather than manual coordination — worth revisiting if contention becomes a real problem.
- Embedding model (`nomic-embed-text` via Ollama) is untouched by this addendum — tracked separately in [#330](https://github.com/Deim0s13/newsbrief/issues/330).

## Addendum (August 2026): Windows Live Validation (#332)

**Status: Confirmed — no model swap needed.** `device_profiles.windows` (`fast=llama3.1:8b`, `balanced=qwen3:14b`, `quality=deepseek-r1:14b`) is validated against live inference on the actual Windows host (RTX 4090 Laptop, Ollama 0.24.0), closing out the risk flagged in the "Update (2026-08-11)" note above.

### `deepseek-r1:14b` thinking-block risk: resolved

The concern was that `deepseek-r1:14b` emits `<think>...</think>` reasoning blocks by default, which `app/llm_output.py` had no explicit handling for before JSON parsing. Investigation found:

- Ollama's thinking-block *separation* into a dedicated `thinking` response field is opt-in via the `think` parameter, not automatic — omitting `think` entirely (the prior behavior across every LLM call site: `stories.py`, `entities.py`, `topics.py`, `llm.py`) risked the raw `<think>` tags leaking directly into the parsed `response` text for any Ollama "thinking" model, not just `deepseek-r1:14b` — this also applies to `qwen3:14b`, the Windows *balanced* model.
- Fixed centrally in `OllamaBackend.generate()` (`app/llm_backends.py`): `think` now defaults to `False` unless a caller explicitly opts in (`stories.py`'s deep-synthesis chain-of-thought mode, #286, still does, unaffected).
- Live-verified on the Windows host post-fix using `scripts/model_fitness.py` (#341) against all three models' real synthesis + entity-extraction prompts: zero `<think>` leakage across all six calls (3 models × 2 tasks), all `parse_ok: true`. `deepseek-r1:14b` does wrap its JSON in a ` ```json ` markdown fence (unlike the other two, which output bare JSON) — a distinct, pre-existing, already-handled quirk (`llm_output.py`'s `markdown_block` extraction strategy), unrelated to thinking blocks.

### Real tok/s vs. LLMfit's live benchmark

| Model | Task | Real tok/s (end-to-end, incl. prefill) | LLMfit `llmfit bench` | Ratio |
|---|---|---|---|---|
| `llama3.1:8b` | entities (short prompt) | ~74 | 92.1 | 80% |
| `qwen3:14b` | entities (short prompt) | ~40 | 49.7 | 80% |
| `deepseek-r1:14b` | entities (short prompt) | ~43 | 51.2 | 84% |

Entity-extraction (short prompt) tok/s is the fairer comparison to LLMfit's pure-decode benchmark; the synthesis task's much longer prompt (full analysis + 3 articles) dilutes the naive tokens/wall-time ratio with prefill time, understating true decode speed for that task specifically — this is a measurement artifact, not a throughput regression. All three models preserve LLMfit's relative ranking (`llama3.1:8b` roughly 2x faster than the other two; `deepseek-r1:14b` marginally ahead of `qwen3:14b`), with a consistent ~80% calibration gap versus LLMfit's benchmark — expected, since real production prompts carry JSON-formatting/instruction overhead that a generic benchmark prompt doesn't.

### Decision

Confirmed final — no changes to `device_profiles.windows`. [#332](https://github.com/Deim0s13/newsbrief/issues/332) closed.

## Addendum (August 2026): Embedding Model Re-evaluation (#330)

**Status: No change — `nomic-embed-text` retained.** This addendum closes out [#330](https://github.com/Deim0s13/newsbrief/issues/330), the embedding-model re-evaluation this ADR deferred (see the "Operational notes" note above). Unlike the synthesis-model work above, this evaluation concluded the current choice is still correct — a negative result worth documenting so the question isn't re-litigated without new evidence.

### Trigger and prerequisite

`nomic-embed-text` (768-dim) is what all v0.8.6 RAG features (semantic dedup, retrieval hook, light RAG, historical linking, `/search/semantic`) are built on, and it hadn't been reassessed since it was first chosen. Evaluation was blocked until [#328](https://github.com/Deim0s13/newsbrief/issues/328) (automatic per-article enrichment) closed, since item-level embeddings were not being populated in production before that fix — there was nothing meaningful to benchmark against.

### Methodology

A reusable benchmark script (`scripts/embedding_benchmark.py`) was built to compare candidates against real NewsBrief data rather than published MTEB scores, using a domain-specific retrieval-precision proxy: articles the pipeline's own clustering already grouped into the same multi-article story are ground-truth "related" pairs. For each embedding model, every sampled item's title+summary text is embedded, and the script checks whether at least one same-story sibling appears in that item's top-5 nearest neighbours by cosine similarity.

An initial run at `--sample-size 200` (a ~17% subsample of the eligible population) showed `qwen3-embedding:0.6b` beating the baseline by ~2pp — but a second 200-item run (different random subsample) showed it *losing* to the baseline by ~4pp. That swing, larger than the effect being measured, made small subsamples untrustworthy for this decision; the benchmark was re-run against the (near-)full multi-article population instead (781 of ~1186 eligible items, 238 stories) for a stable result.

### Candidates evaluated

| Model | Dims | Hit-rate (top-5) | Mean embed latency |
|---|---|---|---|
| `nomic-embed-text` (baseline) | 768 | 49.4% | — (existing production embeddings reused) |
| `qwen3-embedding:0.6b` (native) | 1024 | 48.7% | 115.7ms |
| `qwen3-embedding:0.6b` (MRL-truncated to 768) | 768 | 47.8% | 115.7ms |
| `mxbai-embed-large` (native) | 1024 | 49.8% | 46.1ms |
| `mxbai-embed-large` (naive-truncated to 768)† | 768 | 48.9% | 46.1ms |

† `mxbai-embed-large` is not MRL-trained, so its truncated row is a naive dimension slice, not a principled operation — included for completeness only.

`bge-m3` (multilingual + hybrid dense/sparse) was not evaluated — the issue itself flagged it as likely overkill for an English-only corpus, and the two candidates tested already showed no meaningful gain, so there was no signal to chase further.

### Decision

**No change.** All four candidate variants land within ~1.6pp of the baseline — within noise, not a real improvement. `qwen3-embedding:0.6b`'s published MTEB advantage over `nomic-embed-text` does not carry over to this corpus/task. `mxbai-embed-large` embeds ~2.5x faster, but a latency win alone doesn't justify a schema-adjacent migration (re-embed backfill + re-tuning `semantic_dedupe.threshold`/`light_rag.threshold`/`retrieval_hook.threshold` in `data/model_config.json`) for zero precision gain. MRL truncation to 768-dim was confirmed to work as advertised for the one MRL-trained candidate tested (`qwen3-embedding:0.6b`: 48.7% native vs. 47.8% truncated) — i.e. the no-schema-migration path is viable *if* a future candidate ever justifies adopting it.

### Re-evaluation trigger

Revisit when a genuinely newer-generation embedding model becomes available (this evaluation is a point-in-time comparison against 2026-era candidates, same caveat as the synthesis-model addendum above), or when the corpus grows enough that low sample sizes stop being the limiting factor. `scripts/embedding_benchmark.py` is kept in the repo for that future re-run rather than being a one-off script.
