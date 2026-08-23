#!/usr/bin/env bash
# Idempotent startup script: start kind cluster, confirm ArgoCD is ready,
# trigger ArgoCD sync, and re-establish kubectl port-forwards.
# Called by launchd (macOS) on login, or manually via `make infra-start`.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLUSTER_NAME="newsbrief-dev"
CLUSTER_CONFIG="${PROJECT_ROOT}/k8s/kind/cluster-config.yaml"
LOG_PREFIX="[newsbrief-infra]"

log() { echo "${LOG_PREFIX} $*"; }

# 1. Ensure the Compose DB (only) is running — that's the single Compose
# dependency K8s prod actually needs (host.containers.internal:5432).
#
# NOTE: `up -d db` (not a bare `up -d`) is deliberate (#325) — a bare `up -d`
# also brings up the standalone `api`/`proxy` Compose services, a stale
# duplicate of the real K8s-based prod (namespace newsbrief-prod, ADR-0032)
# with no auto-update mechanism on macOS. That duplicate silently came back
# to life via this exact script more than once. See `make deploy-db-only`,
# which this mirrors.
#
# Use `podman-compose` (standalone tool), not `podman compose` (Podman's
# built-in dispatcher) — the latter can auto-select an external provider such
# as Docker Compose v2 if one is on PATH, which doesn't understand Podman
# secrets ("unsupported external secret db_password"). `make deploy`/`make up`
# use the same standalone `podman-compose` for this reason.
log "Starting Podman Compose DB (prod dependency only, not api/proxy)..."
cd "${PROJECT_ROOT}"
podman-compose -f compose.yaml -f compose.prod.yaml up -d db 2>&1 | sed "s/^/${LOG_PREFIX} /" || \
    log "Warning: podman-compose up failed — API pods may not reach the DB"
cd - >/dev/null

# 2. Ensure kind cluster exists (create if not)
#
# NOTE: `kind get clusters` is used here via a direct podman query rather than
# the `kind get clusters` CLI subcommand. Podman >=6.0.0 changed `podman ps
# --format` to render .Labels as a slice instead of a map, which breaks kind's
# podman-provider ListClusters/create-cluster existence check
# (https://github.com/kubernetes-sigs/kind/issues/4201, fixed upstream on
# kind's main branch but not yet in a tagged release). Other kind subcommands
# (export kubeconfig, get nodes) are unaffected, so we only need to work
# around cluster *detection* here.
if podman ps -a --filter "label=io.x-k8s.kind.cluster=${CLUSTER_NAME}" --format '{{.Names}}' 2>/dev/null | grep -q .; then
    log "Kind cluster '${CLUSTER_NAME}' already exists"
    podman start "${CLUSTER_NAME}-control-plane" >/dev/null 2>&1 || true
else
    log "Creating kind cluster '${CLUSTER_NAME}'..."
    log "(if this fails with 'cannot index slice/array with type string', see" \
        "https://github.com/kubernetes-sigs/kind/issues/4201 — you'll need a" \
        "kind build newer than v0.32.0, or a podman <6.0.0 client, to create a" \
        "brand-new cluster until kind ships a fixed release)"
    kind create cluster --name "${CLUSTER_NAME}" --config "${CLUSTER_CONFIG}"
fi

# 3. Export kubeconfig so kubectl commands work
kind export kubeconfig --name "${CLUSTER_NAME}"
log "Kubeconfig set to cluster '${CLUSTER_NAME}'"

# 4. (removed) Local kind registry setup -- superseded by ADR-0020: all
# images now come from GHCR (ghcr.io/deim0s13/newsbrief), pulled directly by
# ArgoCD-managed pods. See scripts/archive/setup-kind-registry.sh.

# 5. Wait for ArgoCD server to be available
log "Waiting for ArgoCD server..."
kubectl wait \
    --for=condition=available \
    deployment/argocd-server \
    -n argocd \
    --timeout=180s

log "ArgoCD is ready"

# 6. Ensure ArgoCD Application CRs exist — cluster recreation wipes them
if ! kubectl get application newsbrief-prod -n argocd >/dev/null 2>&1; then
    log "ArgoCD Applications not found — applying from k8s/argocd/..."
    kubectl apply -f "${PROJECT_ROOT}/k8s/argocd/"
    log "Applications registered"
else
    log "ArgoCD Applications already registered"
fi

# 7. Trigger sync for both apps (async — auto-sync will also pick these up)
argocd app sync newsbrief-dev --async 2>/dev/null \
    && log "Triggered sync: newsbrief-dev" \
    || log "Warning: could not trigger newsbrief-dev sync (ArgoCD CLI not logged in?)"

argocd app sync newsbrief-prod --async 2>/dev/null \
    && log "Triggered sync: newsbrief-prod" \
    || log "Warning: could not trigger newsbrief-prod sync"

# 8. Re-establish port-forwards (kill any stale ones first)
pkill -f "kubectl port-forward" 2>/dev/null || true
sleep 1

kubectl port-forward svc/newsbrief -n newsbrief-prod --address 0.0.0.0 8788:8787 \
    >> "${PROJECT_ROOT}/logs/port-forward.log" 2>&1 &
kubectl port-forward svc/newsbrief -n newsbrief-dev --address 0.0.0.0 8789:8787 \
    >> "${PROJECT_ROOT}/logs/port-forward.log" 2>&1 &
kubectl port-forward svc/argocd-server -n argocd 8443:443 \
    >> "${PROJECT_ROOT}/logs/port-forward.log" 2>&1 &

log "Port-forwards started:"
log "  Prod app:     http://localhost:8788"
log "  Dev app:      http://localhost:8789"
log "  ArgoCD UI:    https://localhost:8443"
log "NewsBrief infrastructure ready."
