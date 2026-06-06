#!/usr/bin/env bash
# Push current dev branch to origin, then run Tekton ci-dev on the cluster.
# Use this instead of raw git push when you want automatic CI (no Smee required).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

BRANCH="$(git symbolic-ref -q --short HEAD 2>/dev/null || true)"
if [ -z "${BRANCH}" ]; then
  echo "error: detached HEAD; checkout dev before push-dev" >&2
  exit 1
fi
if [ "${BRANCH}" != "dev" ]; then
  echo "error: push-dev must run on branch 'dev' (currently: ${BRANCH})" >&2
  echo "       tip: git checkout dev" >&2
  exit 1
fi

if [ "${SKIP_CI_DEV:-}" = "1" ]; then
  echo "SKIP_CI_DEV=1 — pushing only, not starting pipeline"
  exec git push origin dev "$@"
fi

git push origin dev "$@"
echo ""
echo "Starting ci-dev on cluster..."
exec "${ROOT}/scripts/trigger-ci-dev.sh"
