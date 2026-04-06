#!/usr/bin/env bash
# Manually start Tekton ci-prod. Release version comes from pyproject.toml [project].version
# unless CI_PROD_VERSION_OVERRIDE is set (emergency only).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NS="${TEKTON_NAMESPACE:-default}"
REPO_URL="${CI_PROD_REPO_URL:-https://github.com/Deim0s13/newsbrief.git}"
REV="${CI_PROD_REVISION:-main}"
REG="${CI_PROD_IMAGE_REGISTRY:-kind-registry:5000}"
NAME="${CI_PROD_IMAGE_NAME:-newsbrief}"
BUILD_TAG="${CI_PROD_BUILD_TAG:-latest}"

if ! command -v kubectl >/dev/null 2>&1; then
  echo "error: kubectl not found in PATH" >&2
  exit 1
fi
if ! command -v tkn >/dev/null 2>&1; then
  echo "error: tkn (Tekton CLI) not found in PATH" >&2
  exit 1
fi
if ! kubectl cluster-info >/dev/null 2>&1; then
  echo "error: kubectl cannot reach a cluster" >&2
  exit 1
fi

WS_SRC="name=source,volumeClaimTemplateFile=${ROOT}/tekton/pipelineruns/workspace-template.yaml"
WS_SBOM="name=sbom-output,volumeClaimTemplateFile=${ROOT}/tekton/pipelineruns/workspace-template.yaml"
if [ ! -f "${ROOT}/tekton/pipelineruns/workspace-template.yaml" ]; then
  echo "error: workspace template missing" >&2
  exit 1
fi

EXTRA=()
if [ -n "${CI_PROD_VERSION_OVERRIDE:-}" ]; then
  EXTRA+=(-p "version-override=${CI_PROD_VERSION_OVERRIDE}")
  echo "Starting ci-prod (override version=${CI_PROD_VERSION_OVERRIDE})..."
else
  echo "Starting ci-prod (release version from pyproject on ${REV})..."
fi

cd "${ROOT}"
exec tkn pipeline start ci-prod -n "${NS}" \
  -w "${WS_SRC}" \
  -w "${WS_SBOM}" \
  -s tekton-pipeline \
  -p "repo-url=${REPO_URL}" \
  -p "revision=${REV}" \
  -p "image-registry=${REG}" \
  -p "image-name=${NAME}" \
  -p "build-tag=${BUILD_TAG}" \
  "${EXTRA[@]}" \
  --showlog
