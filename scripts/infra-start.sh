#!/usr/bin/env bash
# Idempotent startup script: start kind cluster, confirm ArgoCD is ready,
# trigger ArgoCD sync, and re-establish kubectl port-forwards.
# Called by launchd (macOS) on login, or manually via `make infra-start`.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLUSTER_NAME="newsbrief-dev"
CLUSTER_CONFIG="${PROJECT_ROOT}/kind/cluster-config.yaml"
LOG_PREFIX="[newsbrief-infra]"

log() { echo "${LOG_PREFIX} $*"; }

# 1. Ensure kind cluster exists (create if not)
if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
    log "Kind cluster '${CLUSTER_NAME}' already exists"
else
    log "Creating kind cluster '${CLUSTER_NAME}'..."
    kind create cluster --name "${CLUSTER_NAME}" --config "${CLUSTER_CONFIG}"
fi

# 2. Export kubeconfig so kubectl commands work
kind export kubeconfig --name "${CLUSTER_NAME}"
log "Kubeconfig set to cluster '${CLUSTER_NAME}'"

# 3. Ensure local registry is connected (for cluster-internal workloads)
if [ -f "${PROJECT_ROOT}/scripts/setup-kind-registry.sh" ]; then
    bash "${PROJECT_ROOT}/scripts/setup-kind-registry.sh" >/dev/null 2>&1 || true
fi

# 4. Wait for ArgoCD server to be available
log "Waiting for ArgoCD server..."
kubectl wait \
    --for=condition=available \
    deployment/argocd-server \
    -n argocd \
    --timeout=180s

log "ArgoCD is ready"

# 5. Trigger sync for both apps (async — ArgoCD will reconcile)
argocd app sync newsbrief-dev --async 2>/dev/null \
    && log "Triggered sync: newsbrief-dev" \
    || log "Warning: could not sync newsbrief-dev (ArgoCD CLI not configured?)"

argocd app sync newsbrief-prod --async 2>/dev/null \
    && log "Triggered sync: newsbrief-prod" \
    || log "Warning: could not sync newsbrief-prod"

# 6. Re-establish port-forwards (kill any stale ones first)
pkill -f "kubectl port-forward" 2>/dev/null || true
sleep 1

kubectl port-forward svc/newsbrief -n newsbrief-prod --address 0.0.0.0 8788:8787 \
    >> "${PROJECT_ROOT}/logs/port-forward.log" 2>&1 &
kubectl port-forward svc/newsbrief -n newsbrief-dev --address 0.0.0.0 8789:8787 \
    >> "${PROJECT_ROOT}/logs/port-forward.log" 2>&1 &
kubectl port-forward svc/argocd-server -n argocd 8443:443 \
    >> "${PROJECT_ROOT}/logs/port-forward.log" 2>&1 &
kubectl port-forward svc/tekton-dashboard -n tekton-pipelines 9097:9097 \
    >> "${PROJECT_ROOT}/logs/port-forward.log" 2>&1 &

log "Port-forwards started:"
log "  Prod app:     http://localhost:8788"
log "  Dev app:      http://localhost:8789"
log "  ArgoCD UI:    https://localhost:8443"
log "  Tekton UI:    http://localhost:9097"
log "NewsBrief infrastructure ready."
