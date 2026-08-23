#!/usr/bin/env bash
# Periodic drift check: compares the image tag actually running in each K8s
# namespace against what Git (the ArgoCD source of truth) says it should be.
#
# Why this exists (#325): ArgoCD's own Application sync status has proven
# unreliable on this kind-on-Podman setup — the application-controller
# intermittently can't resolve `argocd-redis` over cluster DNS, which makes
# auto-sync silently stop working while the UI/CLI still shows a plausible
# status. In the worst case observed so far, both `newsbrief-dev` and
# `newsbrief-prod` ran images weeks out of date with no alert. This script is
# a lightweight, ArgoCD-independent safety net — it talks to Git and the K8s
# API directly, never to ArgoCD — so it still catches drift even while
# ArgoCD's own status reporting is broken.
#
# Not a fix for the underlying DNS flakiness (see #325 for that investigation)
# — just makes silent staleness visible instead of invisible.
#
# Usage: scripts/k8s-version-check.sh
# Run manually, or on a schedule via launchd (see launchd/com.newsbrief.versioncheck.plist).
set -u

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="${PROJECT_ROOT}/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/k8s-version-check.log"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG_FILE"; }

# Load NTFY_TOPIC from .env if present (fail silently if absent)
NTFY_TOPIC=""
if [ -f "${PROJECT_ROOT}/.env" ]; then
    NTFY_TOPIC="$(grep '^NTFY_TOPIC=' "${PROJECT_ROOT}/.env" 2>/dev/null | cut -d= -f2- | tr -d '"')"
fi

notify() {
    local title="$1"
    local message="$2"
    log "ALERT: ${title}: ${message}"
    if [ -n "$NTFY_TOPIC" ]; then
        curl -s -m 10 -H "Title: ${title}" -H "Priority: default" \
            -d "$message" "https://ntfy.sh/${NTFY_TOPIC}" >/dev/null 2>&1 \
            || log "  (ntfy notification failed, non-fatal)"
    fi
}

cd "$PROJECT_ROOT" || exit 0
git fetch origin dev main --quiet 2>>"$LOG_FILE"

check_env() {
    local env_name="$1" branch="$2" namespace="$3" port="$4"

    local expected_tag
    expected_tag="$(git show "origin/${branch}:k8s/overlays/${env_name}/kustomization.yaml" 2>/dev/null \
        | awk '/newTag:/ {print $2; exit}')"
    if [ -z "$expected_tag" ]; then
        log "${env_name}: could not read expected tag from origin/${branch} — skipping"
        return
    fi

    local actual_image
    actual_image="$(kubectl get pods -n "$namespace" -l app.kubernetes.io/name=newsbrief \
        -o jsonpath='{.items[0].spec.containers[0].image}' 2>/dev/null)"
    if [ -z "$actual_image" ]; then
        notify "NewsBrief ${env_name}: no pods found" \
            "namespace=${namespace} has no running newsbrief pods (expected tag: ${expected_tag})"
        return
    fi
    local actual_tag="${actual_image##*:}"

    if [ "$actual_tag" != "$expected_tag" ]; then
        notify "NewsBrief ${env_name}: version drift" \
            "Running ${actual_tag}, but origin/${branch} expects ${expected_tag}. ArgoCD may not have synced."
    else
        log "${env_name}: OK (${actual_tag})"
    fi

    local health
    health="$(curl -s -m 8 "http://localhost:${port}/health" 2>/dev/null)"
    if [ -z "$health" ]; then
        notify "NewsBrief ${env_name}: unreachable" \
            "http://localhost:${port}/health did not respond"
    elif ! echo "$health" | grep -q '"status":"healthy"'; then
        notify "NewsBrief ${env_name}: unhealthy" "$health"
    fi
}

check_env dev dev newsbrief-dev 8789
check_env prod main newsbrief-prod 8788

log "check complete"
