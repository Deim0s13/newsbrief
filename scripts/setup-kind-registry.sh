#!/bin/bash
# Setup local registry for kind cluster
# Based on: https://kind.sigs.k8s.io/docs/user/local-registry/

set -e

REGISTRY_NAME="${REGISTRY_NAME:-kind-registry}"
REGISTRY_PORT="${REGISTRY_PORT:-5000}"
KIND_CLUSTER_NAME="${KIND_CLUSTER_NAME:-newsbrief-dev}"

echo "🐳 Setting up local registry for kind..."

# 1. Create registry container if not running
if [ "$(docker inspect -f '{{.State.Running}}' "${REGISTRY_NAME}" 2>/dev/null || true)" != 'true' ]; then
  echo "📦 Creating registry container..."
  docker run -d --restart=always -p "127.0.0.1:${REGISTRY_PORT}:5000" \
    --network bridge \
    --name "${REGISTRY_NAME}" \
    registry:2
  echo "✅ Registry container created"
else
  echo "✅ Registry container already running"
fi

# 2. Create kind cluster with containerd registry config
if ! kind get clusters | grep -q "^${KIND_CLUSTER_NAME}$"; then
  echo "🔧 Creating kind cluster: ${KIND_CLUSTER_NAME}..."

  # Create cluster config
  cat <<EOF | kind create cluster --name "${KIND_CLUSTER_NAME}" --config=-
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
  echo "✅ Kind cluster created"
else
  echo "✅ Kind cluster already exists"
fi

# 3. Connect registry to kind network
if [ "$(docker inspect -f='{{json .NetworkSettings.Networks.kind}}' "${REGISTRY_NAME}" 2>/dev/null)" = 'null' ]; then
  echo "🔗 Connecting registry to kind network..."
  docker network connect "kind" "${REGISTRY_NAME}" || true
  echo "✅ Registry connected to kind network"
else
  echo "✅ Registry already connected to kind network"
fi

# 4. Configure containerd to use registry
echo "⚙️  Configuring containerd registry..."
REGISTRY_DIR="/etc/containerd/certs.d/localhost:${REGISTRY_PORT}"
for node in $(kind get nodes --name "${KIND_CLUSTER_NAME}"); do
  docker exec "${node}" mkdir -p "${REGISTRY_DIR}"
  cat <<EOF | docker exec -i "${node}" cp /dev/stdin "${REGISTRY_DIR}/hosts.toml"
[host."http://${REGISTRY_NAME}:5000"]
EOF
done
echo "✅ Containerd configured"

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
echo "✅ Registry ConfigMap created"

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  🎉 Local registry setup complete!"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "  Registry URL: localhost:${REGISTRY_PORT}"
echo "  Kind Cluster: ${KIND_CLUSTER_NAME}"
echo ""
echo "  Usage:"
echo "    docker tag myimage localhost:${REGISTRY_PORT}/myimage:tag"
echo "    docker push localhost:${REGISTRY_PORT}/myimage:tag"
echo ""
echo "  In Kubernetes manifests:"
echo "    image: localhost:${REGISTRY_PORT}/newsbrief:v0.7.5"
echo ""
