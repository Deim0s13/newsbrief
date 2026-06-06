#!/usr/bin/env bash
# Check GHCR for a newer image; redeploy + migrate if one is found.
# Called by Windows Task Scheduler every 15 minutes.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

# Load .env so NTFY_TOPIC is available (fail silently if absent)
if [ -f .env ]; then
    set -a
    # shellcheck source=/dev/null
    source .env
    set +a
fi

IMAGE="ghcr.io/deim0s13/newsbrief:latest"
mkdir -p logs
LOG="logs/compose-watch.log"

log() { echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') $*" | tee -a "$LOG"; }

# Wait for Podman (may be called right after boot)
for i in $(seq 1 10); do
    podman info >/dev/null 2>&1 && break
    log "Waiting for Podman... ($i/10)"
    sleep 3
done

if ! podman info >/dev/null 2>&1; then
    log "Podman not available. Skipping update check."
    exit 0
fi

RUNNING_DIGEST=$(podman inspect newsbrief --format '{{.ImageDigest}}' 2>/dev/null || echo "")

log "Pulling $IMAGE..."
if ! podman pull "$IMAGE" --quiet 2>/dev/null; then
    log "Could not pull image (offline?). Skipping."
    exit 0
fi

LATEST_DIGEST=$(podman image inspect "$IMAGE" --format '{{.Digest}}' 2>/dev/null || echo "")

if [ -z "$LATEST_DIGEST" ]; then
    log "Could not determine latest digest. Skipping."
    exit 0
fi

if [ "$RUNNING_DIGEST" = "$LATEST_DIGEST" ]; then
    log "Already at latest ($LATEST_DIGEST). No action needed."
    exit 0
fi

log "New image detected. Deploying..."
podman-compose -f compose.yaml -f compose.prod.yaml up -d

log "Waiting for database..."
until podman exec newsbrief-db pg_isready -U newsbrief -d newsbrief >/dev/null 2>&1; do
    sleep 2
done

log "Running migrations..."
podman-compose -f compose.yaml -f compose.prod.yaml exec -T api alembic upgrade head

log "Deploy complete: $LATEST_DIGEST"

if [ -n "${NTFY_TOPIC:-}" ]; then
    curl -s -X POST \
        -H "Title: NewsBrief auto-deployed" \
        -H "Priority: default" \
        -d "New version deployed on $(hostname -s)" \
        "https://ntfy.sh/${NTFY_TOPIC}" >/dev/null || true
fi
