# ADR 0029: Adopt pipeline-oriented orchestration for story processing

## Status

Accepted

## Date

February 2026

## Context

NewsBrief today processes articles and stories through a set of **partially manual or loosely connected steps**: scheduled feed refresh, on-demand story generation, manual “generate stories” in the UI, and ad hoc re-runs. There is no explicit lifecycle or state model for an article or story as it moves through ingestion, extraction, enrichment, clustering, synthesis, and publish. This has worked for the current scale but creates real limits:

- **Monitoring** is scheduler-centric, not stage-centric; it is hard to see where items are stuck or how deep each stage’s backlog is.
- **Retries** are implicit (e.g. “run generation again”) rather than targeted; transient failures are not clearly separated from permanent ones, and there is no dead-letter or failed-items workflow.
- **Testing** of the end-to-end flow and of individual stages (including retry and recovery) is harder without explicit state and transitions.
- **Scaling** editorial logic (e.g. retrieval, selective reasoning, context generation, confidence gating) is harder when there is no clear place in the flow to plug them in.

The product goal—synthesized story briefs from RSS with local AI—does not change. What is changing is the **operating model**: how processing is controlled, observed, and extended.

## Decision

**Move to an explicit article/story state model and an orchestrated stage-based pipeline** for story processing.

- **Article-level states** (e.g. discovered, fetched, extracted, enriched, embedded, clustered, failed) and **story-level states** (e.g. candidate, synthesizing, context_enriched, quality_checked, published, archived, failed) are defined, persisted, and used to drive flow.
- A **pipeline runner** advances items through a default sequence of stages (ingest → extract → enrich → cluster → [retrieval] → synthesize → quality-check → publish), with stage interfaces, idempotent execution, and per-stage metadata.
- **Retry, backoff, and dead-letter** handling make failures explicit and recoverable; operators can retry, inspect, or discard failed items.
- **Manual operator actions** (re-fetch, re-extract, re-synthesize, etc.) remain supported but are expressed as targeted, stage-aware actions over the pipeline rather than separate ad hoc workflows.
- **Observability** becomes stage-aware: queue depth, throughput, latency, failure rate, and stuck-item detection per stage, with dashboards/alerts that reflect the pipeline as a workflow.
- **Extension points** are clearly defined: retrieval between clustering and synthesis, synthesis routing (standard vs deep) based on cluster complexity, post-synthesis context generation, and confidence-based publish gating.

This is **pipeline-oriented orchestration**, not a shift to an agentic or autonomous-agent architecture. The system still follows a defined stage sequence; human operators retain control and visibility.

## Consequences

### Positive

- **Reliability**: Explicit state and retries make transient failures recoverable; dead-letter handling prevents silent loss of items.
- **Observability**: Stage-aware monitoring and metrics make it easier to see backlog, latency, and failure hotspots.
- **Testability**: State transitions and stage boundaries are testable; E2E tests can validate the orchestrated flow and recovery paths.
- **Extension**: Retrieval, selective reasoning, context stages, and confidence gates have clear insertion points in the pipeline.
- **Operational clarity**: Manual actions are consistent with the pipeline model instead of bypassing it.

### Negative

- **Orchestration complexity**: More moving parts (state machine, pipeline runner, stage contracts) to design, implement, and maintain.
- **Migration**: Existing code paths must be adapted to write and respect state; rollout may be incremental.

## Non-goal

This ADR does **not** adopt a full agentic or autonomous-agent architecture. The pipeline remains a predetermined sequence of stages with well-defined inputs and outputs. Autonomy, tool use, and open-ended reasoning are out of scope for this decision.

## Implementation notes: reliability, retries, and operator controls (#275 / #277)

The bullets above on **retry, backoff, dead-letter**, **operator actions**, and **observability** are intentionally high level. The following notes constrain and sequence implementation work without replacing issue acceptance criteria or a future short supplement ADR if the team splits “reliability” from “orchestration.”

### Scope of “failure” and granularity

| Grain | What fails visibly | Pros | Cons |
|-------|-------------------|------|------|
| **Coarse (stage run)** | Whole **`ingest`** or **`story_generation`** attempt (already logged in **`pipeline_stage_runs`**) | Small schema change; fast to ship; matches current runner boundaries | One bad cluster/article does not surface as its own row; operators may only see aggregate errors |
| **Fine (entity / job row)** | One **article** or **story** (or inner job) with stage + reason | Matches ADR-0030 **FAILED** semantics; clearer dead-letter queue | Touches **`generate_stories_simple`** / clustering paths; more migration and tests |

**Incremental path:** deliver **stage-run-level** retries, backoff metadata, and terminal flags first, then add **targeted** failure rows (or tighter links to `items` / `stories`) where inner failures are already identifiable, without blocking on a full refactor of story generation.

### Persistence and policy

- **Retry counts**, **next retry time** (or exponential backoff schedule), and **terminal / discarded** disposition should be **persisted** so restarts and multiple replicas do not lose intent.
- **Configuration** (e.g. max attempts, base and max delay) should be **environment- or settings-driven**, not hard-coded, so behaviour is testable and deterministic for a given config.
- **Transient vs permanent** classification can start **conservative** (retry only to a capped `N`, then terminal) and grow smarter (e.g. skip retry on validation errors) without changing the overall model.

### Coupling with [#277](https://github.com/Deim0s13/newsbrief/issues/277) (operator controls)

- **Inspect** and **retry** should reuse **`/api/admin/pipeline/*`** patterns (`replay`, `runs`, and extensions) so operators have one mental model.
- **Discard** (or “dismiss” / **dead-letter** without delete) should be explicit in API and, where applicable, align with **`processing_states`** rules (ADR-0030) so story/article state is not lying.
- Avoid duplicating a second ad hoc “re-run” UX in the admin UI per stage; extend the standardized controls **#277** calls for.

### Observability

- **#275** gives **data** (who failed, when, how many retries); **#276** / **#291** give **telemetry** (metrics/alerts). The runner should emit structured logs and persist enough fields that stage-aware dashboards can be added later without another migration.

### Ordering suggestion (not mandatory)

1. Persist retry / terminal fields and policy for **existing** stage runs (or a sibling **failure** table if cleaner).
2. Implement automatic retries with backoff where safe, plus admin **list/filter** for failed or terminal items.
3. Add **discard** and tighten **retry** paths with **#277**.
4. Deepen **per-entity** failure tracking as story generation internals expose stable targets (tracked in [#293](https://github.com/Deim0s13/newsbrief/issues/293)).

## References

- **Canonical processing state model:** [ADR-0030: Article and story processing states](0030-article-story-processing-states.md) (subordinate specification; does not duplicate this ADR)
- **Ingest idempotency and re-ingest upsert:** [ADR-0031: Pipeline idempotency and article re-ingest](0031-pipeline-idempotency-and-reingest.md), GitHub [#235](https://github.com/Deim0s13/newsbrief/issues/235)
- **Retries, backoff, dead-letter (Phase 1):** GitHub [#275](https://github.com/Deim0s13/newsbrief/issues/275); **standardize operator controls:** [#277](https://github.com/Deim0s13/newsbrief/issues/277); **per-entity failures (Phase 2, after #275):** [#293](https://github.com/Deim0s13/newsbrief/issues/293)
- Pipeline orchestration workstream: GitHub issues [#273](https://github.com/Deim0s13/newsbrief/issues/273)–[#291](https://github.com/Deim0s13/newsbrief/issues/291) (label: `pipeline-orchestration`), tracked in [#292](https://github.com/Deim0s13/newsbrief/issues/292)
- [ARCHITECTURE.md](../ARCHITECTURE.md): Story Processing Pipeline (Section 7.5)
- [ARCHITECTURAL_ROADMAP.md](ARCHITECTURAL_ROADMAP.md): Pipeline orchestration workstream
