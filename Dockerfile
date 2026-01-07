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

# Build arguments for versioning
ARG VERSION=dev
ARG BUILD_DATE
ARG GIT_SHA

# Labels for container metadata (OCI standard)
LABEL org.opencontainers.image.title="NewsBrief"
LABEL org.opencontainers.image.description="Story-based News Aggregator with AI Synthesis"
LABEL org.opencontainers.image.version="${VERSION}"
LABEL org.opencontainers.image.created="${BUILD_DATE}"
LABEL org.opencontainers.image.revision="${GIT_SHA}"
LABEL org.opencontainers.image.source="https://github.com/Deim0s13/newsbrief"
LABEL org.opencontainers.image.licenses="MIT"

# Runtime environment
ENV PYTHONDONTWRITEBYTECODE=1 \
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

# Create data directory with correct permissions
RUN mkdir -p /app/data && chown newsbrief:newsbrief /app/data

# Switch to non-root user
USER newsbrief

# Health check (uses root endpoint until dedicated /health is added in #152)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8787/ || exit 1

EXPOSE 8787

# Default command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8787"]
