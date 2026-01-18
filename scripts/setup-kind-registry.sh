#!/bin/sh
# Setup kind cluster with local registry (Podman-based)
# Based on: https://kind.sigs.k8s.io/docs/user/local-registry/

set -o errexit

# Configuration
REG_NAME='kind-registry'
REG_PORT='5000'
CLUSTER_NAME='newsbrief-dev'

# Detect container runtime
if command -v podman >/dev/null 2>&1; then
  CONTAINER_CMD="podman"
  export KIND_EXPERIMENTAL_PROVIDER=podman
elif command -v docker >/dev/null 2>&1; then
  CONTAINER_CMD="docker"
else
  echo "❌ Error: Neither podman nor docker found"
  exit 1
fi

echo "🚀 Setting up kind cluster with local registry..."
echo "   Container runtime: $CONTAINER_CMD"

# 1. Create registry container if not running
if [ "$($CONTAINER_CMD inspect -f '{{.State.Running}}' "${REG_NAME}" 2>/dev/null || true)" != 'true' ]; then
  echo "📦 Creating registry container..."
  $CONTAINER_CMD run \
    -d --restart=always -p "127.0.0.1:${REG_PORT}:5000" --name "${REG_NAME}" \
    registry:2
else
  echo "✅ Registry already running"
fi

# 2. Delete existing cluster if present
if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
  echo "🗑️  Deleting existing cluster..."
  kind delete cluster --name "${CLUSTER_NAME}"
fi

# 3. Create kind cluster with containerd registry config
echo "🔧 Creating kind cluster..."
cat <<EOF | kind create cluster --name "${CLUSTER_NAME}" --config=-
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
containerdConfigPatches:
- |-
  [plugins."io.containerd.grpc.v1.cri".registry]
    config_path = "/etc/containerd/certs.d"
nodes:
- role: control-plane
  extraPortMappings:
  - containerPort: 30080
    hostPort: 8080
    protocol: TCP
  - containerPort: 30443
    hostPort: 8443
    protocol: TCP
EOF

# 4. Add registry config to nodes (for both localhost:5000 and kind-registry:5000)
echo "📝 Configuring containerd registry..."
for node in $(kind get nodes --name "${CLUSTER_NAME}"); do
  # Config for localhost:5000 (host access)
  REGISTRY_DIR="/etc/containerd/certs.d/localhost:${REG_PORT}"
  $CONTAINER_CMD exec "${node}" mkdir -p "${REGISTRY_DIR}"
  cat <<EOF | $CONTAINER_CMD exec -i "${node}" cp /dev/stdin "${REGISTRY_DIR}/hosts.toml"
[host."http://${REG_NAME}:5000"]
EOF
  # Config for kind-registry:5000 (in-cluster access via DNS)
  REGISTRY_DIR="/etc/containerd/certs.d/${REG_NAME}:${REG_PORT}"
  $CONTAINER_CMD exec "${node}" mkdir -p "${REGISTRY_DIR}"
  cat <<EOF | $CONTAINER_CMD exec -i "${node}" cp /dev/stdin "${REGISTRY_DIR}/hosts.toml"
[host."http://${REG_NAME}:5000"]
EOF
done

# 5. Connect registry to kind network (for podman, need different approach)
if [ "$CONTAINER_CMD" = "docker" ]; then
  if [ "$($CONTAINER_CMD inspect -f='{{json .NetworkSettings.Networks.kind}}' "${REG_NAME}")" = 'null' ]; then
    echo "🔗 Connecting registry to kind network..."
    $CONTAINER_CMD network connect "kind" "${REG_NAME}"
  fi
else
  # For podman, check if already connected
  KIND_NETWORK=$($CONTAINER_CMD network ls --format '{{.Name}}' | grep -E '^kind$' || true)
  if [ -n "$KIND_NETWORK" ]; then
    REG_NETWORKS=$($CONTAINER_CMD inspect "${REG_NAME}" --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' 2>/dev/null || echo "")
    if ! echo "$REG_NETWORKS" | grep -q "kind"; then
      echo "🔗 Connecting registry to kind network..."
      $CONTAINER_CMD network connect "kind" "${REG_NAME}" 2>/dev/null || true
    fi
  fi
fi

# 6. Document the registry for tools (like Tilt, Skaffold)
echo "📋 Creating registry ConfigMap..."
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: local-registry-hosting
  namespace: kube-public
data:
  localRegistryHosting.v1: |
    host: "localhost:${REG_PORT}"
    help: "https://kind.sigs.k8s.io/docs/user/local-registry/"
EOF

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "✅ Kind cluster '${CLUSTER_NAME}' with local registry created!"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "Registry: localhost:${REG_PORT}"
echo ""
echo "Next steps:"
echo "  1. Install Tekton:     kubectl apply -f https://storage.googleapis.com/tekton-releases/pipeline/latest/release.yaml"
echo "  2. Install Triggers:   kubectl apply -f https://storage.googleapis.com/tekton-releases/triggers/latest/release.yaml"
echo "  3. Install Interceptors: kubectl apply -f https://storage.googleapis.com/tekton-releases/triggers/latest/interceptors.yaml"
echo "  4. Install ArgoCD:     kubectl create namespace argocd && kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml"
echo "  5. Apply RBAC:         kubectl apply -f k8s/infrastructure/tekton-rbac.yaml"
echo "  6. Apply Tekton tasks: kubectl apply -f tekton/tasks/"
echo "  7. Apply pipelines:    kubectl apply -f tekton/pipelines/"
echo "  8. Apply triggers:     kubectl apply -f tekton/triggers/"
echo "  9. Apply ArgoCD apps:  kubectl apply -f k8s/argocd/"
echo ""
