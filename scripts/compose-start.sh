#!/usr/bin/env bash
# Idempotent Compose stack startup. Called by Windows Task Scheduler on login.
# Safe to call repeatedly — podman-compose up -d is a no-op when already running.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

log() { echo "[newsbrief-start] $(date -u '+%Y-%m-%dT%H:%M:%SZ') $*"; }

# Wait for Podman to become available (Podman Desktop may still be initialising)
for i in $(seq 1 20); do
    podman info >/dev/null 2>&1 && break
    log "Waiting for Podman... ($i/20)"
    sleep 3
done

podman info >/dev/null 2>&1 || { log "ERROR: Podman not available after 60s. Exiting."; exit 1; }

log "Starting Compose stack..."
podman-compose -f compose.yaml -f compose.prod.yaml up -d
log "Stack is up."
