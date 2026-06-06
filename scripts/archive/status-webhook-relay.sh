#!/usr/bin/env bash
# Health: EventListener on LOCAL_PORT + smee-client + github-webhook-secret.
set -euo pipefail

PORT="${LOCAL_PORT:-8080}"
CHANNEL_ID="cddqBCYHwHG3ZcUY"
port_ok=0
smee_ok=0
secret_ok=0

if command -v lsof >/dev/null 2>&1; then
  if lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "status: port ${PORT} listening (EventListener port-forward)"
    port_ok=1
  else
    echo "status: port ${PORT} not listening — run: make port-forwards"
  fi
else
  echo "status: install lsof for port check; assuming port ok"
  port_ok=1
fi

if pgrep -f "smee-client.*${CHANNEL_ID}" >/dev/null 2>&1; then
  echo "status: smee-client running (GitHub → :${PORT})"
  smee_ok=1
else
  echo "status: smee-client not running — run: make port-forwards"
fi

if command -v kubectl >/dev/null 2>&1 && kubectl cluster-info >/dev/null 2>&1; then
  if kubectl get secret github-webhook-secret -n default >/dev/null 2>&1; then
    echo "status: secret github-webhook-secret present"
    secret_ok=1
  else
    echo "status: missing github-webhook-secret in default — see docs/development/KUBERNETES.md"
  fi
else
  echo "status: kubectl cluster not reachable (cannot verify secret)"
fi

if [ "${port_ok}" -eq 1 ] && [ "${smee_ok}" -eq 1 ] && [ "${secret_ok}" -eq 1 ]; then
  exit 0
fi
echo "status: unhealthy — fix items above"
exit 1
