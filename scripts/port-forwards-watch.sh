#!/bin/bash
# Supervises the kubectl port-forwards NewsBrief depends on (prod:8788, dev:8789,
# ArgoCD UI:8443). `kubectl port-forward` has no built-in reconnect: it exits
# whenever the underlying connection drops (laptop sleep/wake, network blips, the
# kind node restarting, etc.), silently leaving the app unreachable. launchd
# (com.newsbrief.portforwards.plist) keeps this script itself alive via KeepAlive;
# this script in turn polls each individual port-forward child and restarts any
# that have exited.
#
# NOTE: macOS ships bash 3.2 at /bin/bash (no associative arrays), so this
# intentionally uses plain variables rather than `declare -A`.
set -u

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="${PROJECT_ROOT}/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/port-forwards-watch.log"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >>"$LOG_FILE"; }

PROD_PID=0
DEV_PID=0
ARGOCD_PID=0

cmd_for() {
    case "$1" in
    prod) echo "kubectl port-forward svc/newsbrief -n newsbrief-prod --address 0.0.0.0 8788:8787" ;;
    dev) echo "kubectl port-forward svc/newsbrief -n newsbrief-dev --address 0.0.0.0 8789:8787" ;;
    argocd) echo "kubectl port-forward svc/argocd-server -n argocd 8443:443" ;;
    esac
}

pid_for() {
    case "$1" in
    prod) echo "$PROD_PID" ;;
    dev) echo "$DEV_PID" ;;
    argocd) echo "$ARGOCD_PID" ;;
    esac
}

set_pid() {
    case "$1" in
    prod) PROD_PID="$2" ;;
    dev) DEV_PID="$2" ;;
    argocd) ARGOCD_PID="$2" ;;
    esac
}

start_one() {
    local name="$1"
    # shellcheck disable=SC2046
    $(cmd_for "$name") >>"$LOG_FILE" 2>&1 &
    set_pid "$name" "$!"
    log "started ${name} port-forward (pid $(pid_for "$name"))"
}

cleanup() {
    log "stopping (received signal)"
    for name in prod dev argocd; do
        pid="$(pid_for "$name")"
        [ "$pid" != "0" ] && kill "$pid" 2>/dev/null
    done
    exit 0
}
trap cleanup TERM INT

log "port-forwards-watch starting"
for name in prod dev argocd; do
    start_one "$name"
done

while true; do
    sleep 15
    for name in prod dev argocd; do
        pid="$(pid_for "$name")"
        if ! kill -0 "$pid" 2>/dev/null; then
            log "${name} port-forward is down, restarting"
            start_one "$name"
        fi
    done
done
