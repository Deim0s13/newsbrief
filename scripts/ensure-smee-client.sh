#!/usr/bin/env bash
# Start smee-client if not running, forwarding GitHub webhooks to the local EventListener.
# Expects Tekton EventListener to be reachable on LOCAL_PORT (default 8080), e.g. after
# kubectl port-forward svc/el-newsbrief-listener. Called from: make port-forwards
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOGDIR="${ROOT}/logs"
mkdir -p "${LOGDIR}"

SMEE_URL="${SMEE_URL:-https://smee.io/cddqBCYHwHG3ZcUY}"
PORT="${LOCAL_PORT:-8080}"
SMEE_LOG="${LOGDIR}/smee-client.log"
CHANNEL_ID="cddqBCYHwHG3ZcUY"

if pgrep -f "smee-client.*${CHANNEL_ID}" >/dev/null 2>&1; then
  echo "✅ smee-client already running → http://127.0.0.1:${PORT} (log: ${SMEE_LOG})"
  exit 0
fi

if ! command -v npx >/dev/null 2>&1; then
  echo "error: npx not in PATH (install Node.js) — cannot start smee-client" >&2
  exit 1
fi

echo "Waiting for EventListener on port ${PORT}..."
for _ in $(seq 1 45); do
  if command -v lsof >/dev/null 2>&1; then
    if lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
      break
    fi
  else
    # No lsof: brief pause then proceed
    sleep 2
    break
  fi
  sleep 1
done

if command -v lsof >/dev/null 2>&1; then
  if ! lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "error: nothing listening on ${PORT} — run from repo: make port-forwards (kubectl forward comes first)" >&2
    exit 1
  fi
fi

echo "Starting smee-client → http://127.0.0.1:${PORT} (log: ${SMEE_LOG})"
nohup npx --yes smee-client --url "${SMEE_URL}" --target "http://127.0.0.1:${PORT}" >>"${SMEE_LOG}" 2>&1 &
echo "✅ smee-client pid $! — GitHub Payload URL: ${SMEE_URL}"
