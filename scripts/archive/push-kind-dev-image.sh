#!/usr/bin/env bash
# Build the app image from the current Git tree and push dev-latest to the Kind local registry.
# Pods pull it as kind-registry:5000/newsbrief:dev-latest (see k8s/overlays/dev).
# Requires: podman or docker, registry on localhost:5000 (kind-registry), working directory = repo root.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

RUNTIME="${RUNTIME:-}"
if [ -z "${RUNTIME}" ]; then
  if command -v podman >/dev/null 2>&1; then
    RUNTIME=podman
  elif command -v docker >/dev/null 2>&1; then
    RUNTIME=docker
  else
    echo "error: set RUNTIME=podman|docker or install one of them" >&2
    exit 1
  fi
fi

REGISTRY="${KIND_REGISTRY_HOST:-localhost:5000}"
IMAGE="${REGISTRY}/newsbrief:dev-latest"
GIT_SHA="$(git rev-parse HEAD 2>/dev/null || echo unknown)"

echo "🔨 ${RUNTIME} build → ${IMAGE}"
echo "   GIT_SHA=${GIT_SHA}"
"${RUNTIME}" build \
  --build-arg "GIT_SHA=${GIT_SHA}" \
  -t "${IMAGE}" \
  -f Dockerfile \
  .

echo "📤 ${RUNTIME} push ${IMAGE}"
# Kind's local registry is HTTP on localhost — disable TLS verify for push/pull from host
if [ "${RUNTIME}" = "podman" ]; then
  "${RUNTIME}" push --tls-verify=false "${IMAGE}"
else
  # Docker: ensure daemon has "insecure-registries": ["localhost:5000"] or use host that trusts HTTP
  "${RUNTIME}" push "${IMAGE}"
fi

echo "✅ Done. Sync Argo app newsbrief-dev (or wait for self-heal). Stuck migrate Job: kubectl delete job -n newsbrief-dev newsbrief-db-migrate"
