#!/bin/bash
# Setup local registry and kind cluster for NewsBrief development
# Reference: https://kind.sigs.k8s.io/docs/user/local-registry/

set -e

REGISTRY_NAME="kind-registry"
REGISTRY_PORT="5001"
CLUSTER_NAME="newsbrief-dev"

echo "🚀 Setting up local development environment..."

# 1. Create registry container if not running
if ! docker inspect "${REGISTRY_NAME}" &>/dev/null; then
  echo "📦 Creating local registry..."
  docker run -d --restart=always -p "127.0.0.1:${REGISTRY_PORT}:5000" \
    --network bridge \
    --name "${REGISTRY_NAME}" \
    registry:2
else
  echo "✅ Registry '${REGISTRY_NAME}' already exists"
fi

# 2. Delete existing kind cluster if it exists
if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
  echo "🗑️  Deleting existing cluster '${CLUSTER_NAME}'..."
  kind delete cluster --name "${CLUSTER_NAME}"
fi

# 3. Create kind cluster with containerd configured to use local registry
echo "🔧 Creating kind cluster with registry configuration..."
cat <<EOF | kind create cluster --name "${CLUSTER_NAME}" --config=-
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
containerdConfigPatches:
- |-
  [plugins."io.containerd.grpc.v1.cri".registry.mirrors."localhost:${REGISTRY_PORT}"]
    endpoint = ["http://${REGISTRY_NAME}:5000"]
  [plugins."io.containerd.grpc.v1.cri".registry.configs."localhost:${REGISTRY_PORT}".tls]
    insecure_skip_verify = true
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

# 4. Connect registry to kind network
echo "🔗 Connecting registry to kind network..."
if ! docker network connect "kind" "${REGISTRY_NAME}" 2>/dev/null; then
  echo "   (Registry already connected to kind network)"
fi

# 5. Create ConfigMap for registry discovery
echo "📋 Creating registry ConfigMap..."
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: local-registry-hosting
  namespace: kube-public
data:
  localRegistryHosting.v1: |
    host: "localhost:${REGISTRY_PORT}"
    help: "https://kind.sigs.k8s.io/docs/user/local-registry/"
EOF

# 6. Verify registry is accessible from kind
echo "🔍 Verifying registry connectivity..."
docker exec "${CLUSTER_NAME}-control-plane" curl -s "http://${REGISTRY_NAME}:5000/v2/_catalog" > /dev/null && \
  echo "   ✅ Registry accessible from kind nodes" || \
  echo "   ⚠️  Registry may not be accessible - check Docker network"

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "✅ Setup complete!"
echo ""
echo "Registry:  localhost:${REGISTRY_PORT}"
echo "Cluster:   ${CLUSTER_NAME}"
echo ""
echo "Next steps:"
echo "  1. Apply Tekton:  kubectl apply -f tekton/"
echo "  2. Apply ArgoCD:  kubectl apply -f k8s/argocd/"
echo "  3. Build image:   make build-image"
echo "═══════════════════════════════════════════════════════════════"
