#!/usr/bin/env bash
# Stop smee-client for this repo's Smee channel. Does not stop kubectl port-forwards
# (prod 8788, dev 8789, EventListener 8080, Tekton 9097) — use:
#   pkill -f "kubectl port-forward"
# or run make port-forwards again after editing cluster.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PIDFILE="${ROOT}/logs/webhook-relay.pids"
CHANNEL_ID="cddqBCYHwHG3ZcUY"

if pgrep -f "smee-client.*${CHANNEL_ID}" >/dev/null 2>&1; then
  pkill -f "smee-client.*${CHANNEL_ID}" 2>/dev/null || true
  echo "Stopped smee-client (${CHANNEL_ID})."
else
  echo "smee-client (${CHANNEL_ID}) was not running."
fi

# Legacy pidfile from older start-webhook-relay (port-forward + smee PIDs)
if [ -f "${PIDFILE}" ]; then
  while read -r pid; do
    [ -z "${pid}" ] && continue
    if kill -0 "${pid}" 2>/dev/null; then
      echo "Stopping legacy pid ${pid}..."
      kill "${pid}" 2>/dev/null || true
    fi
  done <"${PIDFILE}"
  rm -f "${PIDFILE}"
fi
