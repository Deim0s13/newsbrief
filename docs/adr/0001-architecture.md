# 0001 — Architecture Decision: FastAPI + HTMX + SQLite + Podman + Ollama

## Context
Local-first tech-brief app; private, fast, portable.

## Decision
- FastAPI (API + server-rendered pages with Jinja)
- HTMX for progressive partial updates (no SPA complexity)
- SQLite (FTS5) for persistence & search
- Podman for containerization (Apple Containers experiment later)
- Ollama for local LLM summaries and (later) embeddings

## Consequences
- Simple deploy: `podman run -p 8787:8787`
- Works fully offline (minus live web content)
- Easy to port to OpenShift later