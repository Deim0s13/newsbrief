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

## References

- Pipeline orchestration workstream: GitHub issues [#273](https://github.com/Deim0s13/newsbrief/issues/273)–[#291](https://github.com/Deim0s13/newsbrief/issues/291) (label: `pipeline-orchestration`), tracked in [#292](https://github.com/Deim0s13/newsbrief/issues/292)
- [ARCHITECTURE.md](../ARCHITECTURE.md): Story Processing Pipeline (Section 7.5)
- [ARCHITECTURAL_ROADMAP.md](ARCHITECTURAL_ROADMAP.md): Pipeline orchestration workstream
