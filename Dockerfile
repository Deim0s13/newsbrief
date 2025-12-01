FROM python:3.11-slim

# Build arguments for versioning
ARG VERSION=v0.6.1
ARG BUILD_DATE
ARG GIT_SHA

# Labels for container metadata
LABEL org.opencontainers.image.title="NewsBrief"
LABEL org.opencontainers.image.description="Story-based News Aggregator with AI Synthesis"
LABEL org.opencontainers.image.version="${VERSION}"
LABEL org.opencontainers.image.created="${BUILD_DATE}"
LABEL org.opencontainers.image.revision="${GIT_SHA}"
LABEL org.opencontainers.image.source="https://github.com/Deim0s13/newsbrief"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System deps for lxml/readability
# Note: libxslt1-dev has CVE-2025-7425 (HIGH) - no fix available, required for lxml
# linux-libc-dev kernel headers included for build-time compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libxml2-dev libxslt1-dev libffi-dev curl \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (better layer caching)
# Upgrade pip and setuptools to latest secure versions
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip setuptools && \
    pip install --no-cache-dir -r requirements.txt

# App code
COPY app /app/app
# Make sure data dir exists for SQLite & feeds.opml
RUN mkdir -p /app/data

EXPOSE 8787

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8787"]