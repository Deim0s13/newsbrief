#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PIDFILE="${ROOT}/logs/webhook-relay.pids"

if [ ! -f "${PIDFILE}" ]; then
  echo "No pidfile at ${PIDFILE} (nothing to stop)."
  exit 0
fi

while read -r pid; do
  [ -z "${pid}" ] && continue
  if kill -0 "${pid}" 2>/dev/null; then
    echo "Stopping pid ${pid}..."
    kill "${pid}" 2>/dev/null || true
    sleep 0.5
    kill -9 "${pid}" 2>/dev/null || true
  fi
done <"${PIDFILE}"

rm -f "${PIDFILE}"
echo "Webhook relay stopped."
