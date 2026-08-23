# =============================================================================
# NewsBrief Multi-Stage Dockerfile
# =============================================================================
# Stage 1: Builder - compile dependencies with build tools
# Stage 2: Runtime - minimal production image
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Builder
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS builder

# Install build dependencies for lxml, psycopg, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libxml2-dev \
    libxslt1-dev \
    libffi-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment for clean copy to runtime
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Upgrade pip and install dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r /tmp/requirements.txt

# -----------------------------------------------------------------------------
# Stage 2: Runtime
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

# Build arguments for versioning (pass GIT_SHA from CI so running app matches a Git commit)
ARG VERSION=dev
ARG BUILD_DATE
ARG GIT_SHA=

# Labels for container metadata (OCI standard)
LABEL org.opencontainers.image.title="NewsBrief"
LABEL org.opencontainers.image.description="Story-based News Aggregator with AI Synthesis"
LABEL org.opencontainers.image.version="${VERSION}"
LABEL org.opencontainers.image.created="${BUILD_DATE}"
LABEL org.opencontainers.image.revision="${GIT_SHA}"
LABEL org.opencontainers.image.source="https://github.com/Deim0s13/newsbrief"
LABEL org.opencontainers.image.licenses="MIT"

# NEWSBRIEF_GIT_SHA: surfaced in /health and footer for deploy verification
# NEWSBRIEF_STATE_DIR: where settings.json lives (see #326) -- deployments that
# mount a persistent volume/emptyDir should mount it here, not at /app/data.
ENV NEWSBRIEF_GIT_SHA=${GIT_SHA} \
    NEWSBRIEF_STATE_DIR=/app/state \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Install only runtime libraries (not -dev packages)
# libxml2 and libxslt1.1 are runtime deps for lxml
# libpq5 is runtime dep for psycopg
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 \
    libxslt1.1 \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash newsbrief
WORKDIR /app

# Copy application code
COPY --chown=newsbrief:newsbrief app /app/app
COPY --chown=newsbrief:newsbrief alembic /app/alembic
COPY --chown=newsbrief:newsbrief alembic.ini /app/alembic.ini
COPY --chown=newsbrief:newsbrief pyproject.toml /app/pyproject.toml

# Create data directory and copy default config files.
# /app/data is intentionally NEVER volume-mounted (see #326) -- it must always
# come straight from the image so config changes committed to git actually
# reach running containers. Only settings.json (the one file the app writes
# at runtime) lives under /app/state, which deployments mount/persist instead.
RUN mkdir -p /app/data /app/state && chown newsbrief:newsbrief /app/data /app/state
COPY --chown=newsbrief:newsbrief data/topics.json /app/data/topics.json
COPY --chown=newsbrief:newsbrief data/model_config.json /app/data/model_config.json
COPY --chown=newsbrief:newsbrief data/interests.json /app/data/interests.json
COPY --chown=newsbrief:newsbrief data/source_weights.json /app/data/source_weights.json

# Never ship host-built __pycache__ (wrong Python tag / broken Alembic revision discovery).
RUN find /app -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true

# Switch to non-root user
USER newsbrief

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8787/health || exit 1

EXPOSE 8787

# Default command
# --proxy-headers: Trust X-Forwarded-Proto from Caddy for correct URL generation
# --forwarded-allow-ips: Trust headers from Caddy container (default only trusts 127.0.0.1)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8787", "--proxy-headers", "--forwarded-allow-ips=*"]
