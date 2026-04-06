#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PIDFILE="${ROOT}/logs/webhook-relay.pids"
PORT="${LOCAL_PORT:-8080}"

if [ ! -f "${PIDFILE}" ]; then
  echo "status: not running (no ${PIDFILE})"
  echo "start with: make webhook-relay-start"
  exit 1
fi

pfs=$(sed -n '1p' "${PIDFILE}" || true)
sms=$(sed -n '2p' "${PIDFILE}" || true)
ok=0

if [ -n "${pfs}" ] && kill -0 "${pfs}" 2>/dev/null; then
  echo "status: port-forward pid ${pfs} running"
  ok=1
else
  echo "status: port-forward pid ${pfs:-?} not running"
fi

if [ -n "${sms}" ] && kill -0 "${sms}" 2>/dev/null; then
  echo "status: smee-client pid ${sms} running"
  ok=1
else
  echo "status: smee-client pid ${sms:-?} not running"
fi

if command -v lsof >/dev/null 2>&1; then
  if lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "status: port ${PORT} is listening"
  else
    echo "status: port ${PORT} not listening"
    ok=0
  fi
fi

if [ "${ok}" -eq 1 ]; then
  exit 0
fi
echo "status: unhealthy — run: make webhook-relay-stop && make webhook-relay-start"
exit 1
