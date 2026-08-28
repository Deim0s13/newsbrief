#!/usr/bin/env bash
# Read-only status report for all NewsBrief infra components. Bash port of
# the former ansible/playbooks/status.yml (removed — see docs/adr/0016).
# Called via `make status`.
set -uo pipefail

check() { command -v "$1" >/dev/null 2>&1; }

pass() { echo "✅ $1"; }
fail() { echo "❌ $1"; }

echo
echo "════════════════════════════════════════════════════════════════"
echo "NewsBrief Service Status Report"
echo "════════════════════════════════════════════════════════════════"
echo

echo "Podman Machine:"
if podman info >/dev/null 2>&1; then
    pass "Running"
else
    fail "Not running"
fi
echo

echo "Kind Cluster:"
# NOTE: detect via `podman ps` rather than `kind get clusters` — see the
# matching comment in infra-start.sh (kind's podman-provider cluster
# detection breaks on Podman >=6.0.0, kubernetes-sigs/kind#4201).
if podman ps -a --filter "label=io.x-k8s.kind.cluster=newsbrief-dev" --format '{{.Names}}' 2>/dev/null | grep -q .; then
    pass "newsbrief-dev"
else
    fail "No clusters"
fi
echo

echo "Kubernetes Context:"
if KUBE_CONTEXT="$(kubectl config current-context 2>/dev/null)"; then
    echo "${KUBE_CONTEXT}"
else
    fail "Not configured"
fi
echo

echo "ArgoCD:"
if ARGOCD_PODS="$(kubectl get pods -n argocd --no-headers 2>/dev/null)" && [ -n "${ARGOCD_PODS}" ]; then
    pass "Running"
else
    fail "Not running"
fi
echo

echo "NewsBrief Prod (Kubernetes):"
if PROD_PODS="$(kubectl get pods -n newsbrief-prod --no-headers 2>/dev/null)" && [ -n "${PROD_PODS}" ]; then
    pass "Running"
else
    fail "Not running"
fi
echo

echo "Caddy Proxy:"
CADDY_STATUS="$(podman ps --filter name=newsbrief-proxy --format '{{.Status}}' 2>/dev/null)"
if [ -n "${CADDY_STATUS}" ]; then
    pass "${CADDY_STATUS}"
else
    fail "Not running"
fi
echo

echo "Port Forwards:"
if pgrep -f "kubectl port-forward" >/dev/null 2>&1; then
    pass "Active"
else
    fail "None active"
fi

echo
echo "════════════════════════════════════════════════════════════════"
echo
echo "Dev:  Run 'make dev' locally → http://localhost:8787"
echo "      Kubernetes (Argo newsbrief-dev) → http://localhost:8789"
echo "Prod: http://localhost:8788 (or https://newsbrief.local via Caddy)"
echo
echo "════════════════════════════════════════════════════════════════"
