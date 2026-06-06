#!/usr/bin/env bash
# Build the app image from the current Git tree and push a versioned tag to the Kind local registry.
# Pods pull it as kind-registry:5000/newsbrief:<tag> (see k8s/overlays/prod).
# Usage: scripts/push-kind-prod-image.sh [tag]
#   tag defaults to KIND_PROD_TAG or v0.8.3.1
# Requires: podman or docker, registry on localhost:5000, cwd = repo root.
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

TAG="${1:-${KIND_PROD_TAG:-v0.8.3.1}}"
case "${TAG}" in
  v*) VERSION_LABEL="${TAG#v}" ;;
  *) VERSION_LABEL="${TAG}"; TAG="v${TAG}" ;;
esac

REGISTRY="${KIND_REGISTRY_HOST:-localhost:5000}"
IMAGE="${REGISTRY}/newsbrief:${TAG}"
GIT_SHA="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

echo "🔨 ${RUNTIME} build → ${IMAGE}"
echo "   VERSION_LABEL=${VERSION_LABEL} GIT_SHA=${GIT_SHA}"
"${RUNTIME}" build \
  --build-arg "VERSION=${VERSION_LABEL}" \
  --build-arg "BUILD_DATE=${BUILD_DATE}" \
  --build-arg "GIT_SHA=${GIT_SHA}" \
  -t "${IMAGE}" \
  -f Dockerfile \
  .

echo "📤 ${RUNTIME} push ${IMAGE}"
if [ "${RUNTIME}" = "podman" ]; then
  "${RUNTIME}" push --tls-verify=false "${IMAGE}"
else
  "${RUNTIME}" push "${IMAGE}"
fi

echo "✅ Done. Commit/push k8s/overlays/prod if newTag changed; then refresh Argo app newsbrief-prod."
