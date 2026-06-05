#!/usr/bin/env bash
# Start Tekton ci-dev against the dev branch on GitHub (lint + pytest in cluster).
# Requires: kind/Kubernetes running, Pipeline ci-dev + tasks applied, tkn CLI, kubectl.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NS="${TEKTON_NAMESPACE:-default}"
REPO_URL="${CI_DEV_REPO_URL:-https://github.com/Deim0s13/newsbrief.git}"
REV="${CI_DEV_REVISION:-dev}"

if ! command -v kubectl >/dev/null 2>&1; then
  echo "error: kubectl not found in PATH" >&2
  exit 1
fi
if ! command -v tkn >/dev/null 2>&1; then
  echo "error: tkn (Tekton CLI) not found in PATH" >&2
  exit 1
fi
if ! kubectl cluster-info >/dev/null 2>&1; then
  echo "error: kubectl cannot reach a cluster (is kind up?)" >&2
  exit 1
fi

WS="name=source,volumeClaimTemplateFile=${ROOT}/tekton/pipelineruns/workspace-template.yaml"
if [ ! -f "${ROOT}/tekton/pipelineruns/workspace-template.yaml" ]; then
  echo "error: workspace template missing at tekton/pipelineruns/workspace-template.yaml" >&2
  exit 1
fi

echo "Starting ci-dev (namespace=${NS}, revision=${REV})..."
cd "${ROOT}"
exec tkn pipeline start ci-dev -n "${NS}" \
  --workspace "${WS}" \
  --param "repo-url=${REPO_URL}" \
  --param "revision=${REV}" \
  --showlog
