#!/usr/bin/env bash
# Run kubectl port-forward to the Tekton EventListener and Smee client in the
# background so GitHub webhooks (via smee.io) reach your cluster.
#
# Pair with: scripts/stop-webhook-relay.sh, scripts/status-webhook-relay.sh
# Logs: logs/eventlistener-port-forward.log, logs/smee-client.log (gitignored)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOGDIR="${ROOT}/logs"
mkdir -p "${LOGDIR}"
PIDFILE="${LOGDIR}/webhook-relay.pids"
NS="${EL_NAMESPACE:-default}"
SVC="${EL_SERVICE:-el-newsbrief-listener}"
PORT="${LOCAL_PORT:-8080}"
SMEE_URL="${SMEE_URL:-https://smee.io/cddqBCYHwHG3ZcUY}"
PF_LOG="${LOGDIR}/eventlistener-port-forward.log"
SMEE_LOG="${LOGDIR}/smee-client.log"

if [ -f "${PIDFILE}" ]; then
  pfs=$(sed -n '1p' "${PIDFILE}" || true)
  sms=$(sed -n '2p' "${PIDFILE}" || true)
  alive=0
  [ -n "${pfs}" ] && kill -0 "${pfs}" 2>/dev/null && alive=1
  [ -n "${sms}" ] && kill -0 "${sms}" 2>/dev/null && alive=1
  if [ "${alive}" -eq 1 ]; then
    echo "Webhook relay already running (pidfile ${PIDFILE}). Stop with: make webhook-relay-stop"
    exit 0
  fi
  echo "Removing stale pidfile..."
  rm -f "${PIDFILE}"
fi

if ! command -v kubectl >/dev/null 2>&1; then
  echo "error: kubectl not in PATH" >&2
  exit 1
fi
if ! kubectl cluster-info >/dev/null 2>&1; then
  echo "error: kubectl cannot reach a cluster (start kind / check context)" >&2
  exit 1
fi
if command -v lsof >/dev/null 2>&1; then
  if lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "error: port ${PORT} already in use — free it or set LOCAL_PORT" >&2
    exit 1
  fi
fi
if ! command -v npx >/dev/null 2>&1; then
  echo "error: npx not in PATH (install Node.js / npm)" >&2
  exit 1
fi

echo "Starting port-forward: svc/${SVC} ${PORT}:8080 (ns=${NS})..."
nohup kubectl port-forward "svc/${SVC}" "${PORT}:8080" -n "${NS}" >>"${PF_LOG}" 2>&1 &
PF_PID=$!

i=0
while [ "${i}" -lt 60 ]; do
  if command -v lsof >/dev/null 2>&1; then
    if lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
      break
    fi
  else
    sleep 2
    break
  fi
  if ! kill -0 "${PF_PID}" 2>/dev/null; then
    echo "error: port-forward exited; see ${PF_LOG}" >&2
    tail -20 "${PF_LOG}" >&2 || true
    exit 1
  fi
  sleep 1
  i=$((i + 1))
done

if command -v lsof >/dev/null 2>&1; then
  if ! lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "error: nothing listening on ${PORT}; see ${PF_LOG}" >&2
    kill "${PF_PID}" 2>/dev/null || true
    exit 1
  fi
fi

echo "Starting smee-client → http://localhost:${PORT} ..."
nohup npx --yes smee-client --url "${SMEE_URL}" --target "http://localhost:${PORT}" >>"${SMEE_LOG}" 2>&1 &
SMEE_PID=$!

{
  echo "${PF_PID}"
  echo "${SMEE_PID}"
} >"${PIDFILE}"

echo "Webhook relay running:"
echo "  port-forward pid=${PF_PID}  log=${PF_LOG}"
echo "  smee-client   pid=${SMEE_PID}  log=${SMEE_LOG}"
echo "GitHub push to dev/main should reach Tekton when the webhook URL matches ${SMEE_URL}"
