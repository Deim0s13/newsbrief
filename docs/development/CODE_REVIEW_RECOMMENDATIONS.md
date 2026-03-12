# Code Review Recommendations

This document summarizes an independent code review of the NewsBrief codebase (Feb 2026), including one security fix applied and actionable recommendations for future improvements.

---

## Summary

- **Security**: One SQL injection risk in the story list count query was fixed (parameterized query). Optional topic allowlist validation is recommended.
- **Structure**: `app/main.py` has been split into FastAPI routers (`app/routers/`); main is now the app factory only. See §2.1.
- **Consistency**: Pydantic v2 is in use; `app/models.py` still uses deprecated `@validator`; migrating to `@field_validator` is recommended.
- **Quality**: Pre-existing mypy/lint issues in `main.py`; addressing them would improve type safety and catch bugs earlier.
- **Tests**: Test suite exists; running it in CI and adding coverage for critical paths (e.g. list stories with filters) is recommended.

---

## 1. Security

### 1.1 Fixed: SQL injection in story list count query

**Location**: `app/routers/stories.py` – `list_stories` (total count for pagination). Formerly in `main.py`.

**Issue**: The total count was built by interpolating `status_filter` and `topic` into the SQL string:

```python
conditions.append(f"status = '{status_filter}'")
conditions.append(f"topics_json LIKE '%\"{topic}\"%'")
count_query += " WHERE " + " AND ".join(conditions)
total = s.execute(text(count_query)).scalar()
```

A malicious `topic` (or, in theory, an unexpected `status_filter`) could break out of the string and alter the query.

**Fix applied**: The count query now uses bound parameters:

- `count_params` and `count_parts` build a parameterized `WHERE` clause.
- `status_filter` and a `topic_pattern` (e.g. `f'%"{topic}"%'`) are passed as parameters to `text(count_sql)`.
- No user input is concatenated into the SQL string.

**Recommendation**: Consider validating `topic` against `get_available_topics()` (or a list of topic IDs) before using it in the filter. That limits filter abuse and keeps behavior consistent with the rest of the app.

---

### 1.2 Search and other queries

- **Article search** (`/articles` with `q`): Uses a single bound parameter `:query` with `f"%{search_query}%"`; safe.
- **Stories `get_stories()`** in `app/stories.py`: Uses SQLAlchemy `Story.topics_json.like(f'%"{topic}"%')`, which binds the value; safe.
- **Other `text(...)` usages**: Other reviewed call sites use placeholders and bound parameters (e.g. `:id_0`, `:feed_id`). Remaining risk is in any raw SQL that still builds clauses with f-strings; those should be converted to parameterized queries.

---

## 2. Architecture and structure

### 2.1 Split `app/main.py` into routers ✅ Implemented

**Status**: Done (Phase 3 of Code Improvement Plan). `app/main.py` is now the app factory; routes live in `app/routers/`.

- **Routers in use**: `health.py`, `feeds.py`, `stories.py`, `items.py`, `admin.py`, `config.py`, `pages.py`.
- **Shared dependencies** live in `app/deps.py` (e.g. `session_scope`, `templates`, `get_version`, `limiter`).
- **main.py** configures logging, mounts static/routers, and registers startup/shutdown (scheduler, migrations, credibility import).

When adding new endpoints, add them to the appropriate router under `app/routers/` rather than `main.py`.

---

### 2.2 Database session type

**Location**: `app/db.py` – `session_scope()`.

**Current**: Returns a generic `Iterator`; the actual type is a SQLAlchemy `Session`.

**Recommendation**: Use a more precise type so callers and mypy get better hints, e.g.:

```python
from typing import Iterator
from sqlalchemy.orm import Session

@contextmanager
def session_scope() -> Iterator[Session]:
    sess = SessionLocal()
    ...
```

---

## 3. Pydantic and validation

### 3.1 Prefer Pydantic v2 `field_validator` in `app/models.py`

**Issue**: The project uses `pydantic>=2.7` (v2), but `app/models.py` still uses the v1-style `@validator` (e.g. on `StructuredSummary`, `StoryOut`). `app/llm_output.py` already uses `@field_validator`.

**Recommendation**: In `app/models.py`:

- Replace `from pydantic import ..., validator` with `field_validator` (and `model_validator` where needed).
- Convert each `@validator("field_name")` to `@field_validator("field_name", mode="before")` (or `"after"` as appropriate) and use the v2 signature.

This keeps the codebase consistent and aligned with Pydantic v2, and avoids deprecation warnings or future breakage.

---

### 3.2 Request validation

- **Story list**: `status` and `order_by` are already validated against allowed values; good.
- **Topic**: As above, consider validating `topic` against known topic IDs (e.g. from `get_available_topics()`) and returning 400 for unknown values, to avoid unnecessary DB work and to keep behavior predictable.

---

## 4. Error handling and observability

### 4.1 Broad `except Exception` in story generation

**Location**: `app/main.py` – `generate_stories_endpoint`.

**Current**: A single `except Exception` logs and re-raises an `HTTPException(500, ...)`.

**Recommendation**: Where feasible, catch more specific exceptions (e.g. `ValueError` for “model not available”, DB errors) and map them to appropriate status codes or messages. Keep a top-level `except Exception` only as a last resort and ensure it logs a full traceback (e.g. `exc_info=True`) so production issues are debuggable.

---

### 4.2 Startup migrations and imports

**Location**: `app/main.py` – `_startup()`.

**Current**: Migrations (sanitize summaries, topic migration, credibility import) are wrapped in try/except with warnings; scheduler failure is logged and the app still starts.

**Recommendation**: Document in README or ARCHITECTURE that these are best-effort migrations and that failures are non-fatal. Consider a simple health or readiness flag (“migrations completed”) if you need to gate traffic or monitoring on it later.

---

## 5. Type checking and linting

**Issue**: There are existing mypy/lint findings in `app/main.py` (e.g. `add_exception_handler` signature, `tomllib` redefinition, indexed assignment on `Collection[str]`, default/optional types). These predate the recent count-query fix.

**Recommendation**:

- Run mypy (and your chosen linter) in CI so new code stays clean.
- Fix the reported issues in `main.py` in small batches (e.g. by route or by concern) to avoid a single large refactor.
- Use `# type: ignore` only with a short comment and a tracking issue if a fix is deferred.

---

## 6. Minor and follow-ups

### 6.1 TODO in `app/ranking.py`

**Location**: ~line 423: `# TODO: Implement LLM-based classification`.

**Recommendation**: Either implement it, replace with a keyword-based or hybrid approach, or turn it into a tracked issue and reference it in the comment so it doesn’t get forgotten.

---

### 6.2 Duplicate `get_available_topics`

**Location**: `app/topics.py` and `app/ranking.py` both define `get_available_topics()`.

**Recommendation**: Use a single implementation (e.g. from `app.topics`) and import it in `ranking.py` (and anywhere else that needs it) to avoid drift and duplication.

---

### 6.3 Tests

- **Coverage**: Add at least one test for the story list endpoint with `topic` and `status` filters (and optionally for the count), to guard against regressions in the parameterized count query and filter behavior.
- **CI**: Ensure the test suite runs on every PR (e.g. in existing GitHub Actions). If not already, add a step that runs tests (and optionally mypy) so these recommendations are enforced automatically.

---

## 7. References

- **V0.6.0 Milestone Review**: `docs/archive/project-management/V0.6.0_MILESTONE_REVIEW.md` (code quality, mypy).
- **ADR / Architecture**: `docs/ARCHITECTURE.md`, `docs/adr/` for design context.
- **CI/CD**: `docs/development/CI-CD.md` for pipeline and quality gates.

---

## Checklist (for implementers)

- [x] Parameterize story list count query (done in this review).
- [ ] Validate `topic` against allowed topics (optional but recommended).
- [x] Split `main.py` into routers (done; see §2.1 and CODE_IMPROVEMENT_PLAN Phase 3).
- [ ] Type `session_scope()` as `Iterator[Session]`.
- [ ] Migrate `app/models.py` from `@validator` to `@field_validator`.
- [ ] Fix existing mypy/lint issues in `main.py` and enable in CI.
- [ ] Resolve or track `ranking.py` TODO and consolidate `get_available_topics`.
- [ ] Add tests for story list (and count) with filters; run tests (and mypy) in CI.
