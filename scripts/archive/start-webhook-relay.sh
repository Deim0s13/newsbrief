#!/usr/bin/env bash
# GitHub (Smee) → Tekton: same as a full port-forward refresh + Smee.
# Prefer: make port-forwards (stops stale kubectl forwards, restarts all + smee-client).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"
exec make port-forwards
