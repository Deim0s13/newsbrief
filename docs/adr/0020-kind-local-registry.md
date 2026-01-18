# ADR-0020: Kind Local Registry Configuration

## Status
**Accepted** - January 2026

## Context

NewsBrief uses a local Kubernetes cluster (kind) with an in-cluster container registry for development. The initial setup placed the registry inside the cluster as a Kubernetes deployment, but this caused image pull failures because:

1. **DNS Resolution**: Kind nodes couldn't resolve `registry.registry.svc.cluster.local` from containerd
2. **HTTP vs HTTPS**: Containerd defaults to HTTPS, but the local registry uses HTTP
3. **Network Isolation**: The registry pod runs in a different network namespace than the node's containerd

## Decision

Configure kind with a **host-network local registry** following the [kind documentation](https://kind.sigs.k8s.io/docs/user/local-registry/):

1. Run registry as a Docker container on the host network
2. Connect it to the kind network
3. Configure kind nodes to recognize `localhost:5000` as an insecure registry
4. Use `localhost:5000` as the image reference in all manifests

## Implementation

### 1. Registry Setup Script

```bash
#!/bin/sh
# scripts/setup-kind-registry.sh

set -o errexit

# Registry configuration
REG_NAME='kind-registry'
REG_PORT='5000'

# Create registry container if not running
if [ "$(docker inspect -f '{{.State.Running}}' "${REG_NAME}" 2>/dev/null || true)" != 'true' ]; then
  docker run \
    -d --restart=always -p "127.0.0.1:${REG_PORT}:5000" --network bridge --name "${REG_NAME}" \
    registry:2
fi

# Create kind cluster with containerd registry config
cat <<EOF | kind create cluster --name newsbrief-dev --config=-
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

# Add registry config to nodes
REGISTRY_DIR="/etc/containerd/certs.d/localhost:${REG_PORT}"
for node in $(kind get nodes --name newsbrief-dev); do
  docker exec "${node}" mkdir -p "${REGISTRY_DIR}"
  cat <<EOF | docker exec -i "${node}" cp /dev/stdin "${REGISTRY_DIR}/hosts.toml"
[host."http://${REG_NAME}:5000"]
EOF
done

# Connect registry to kind network
if [ "$(docker inspect -f='{{json .NetworkSettings.Networks.kind}}' "${REG_NAME}")" = 'null' ]; then
  docker network connect "kind" "${REG_NAME}"
fi

# Document the registry for tools
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

echo "✅ Kind cluster with local registry created"
echo "   Registry: localhost:${REG_PORT}"
echo "   Push: docker push localhost:${REG_PORT}/newsbrief:tag"
```

### 2. Updated Image References

All manifests use `localhost:5000` instead of `registry.registry.svc.cluster.local:5000`:

```yaml
# k8s/base/deployment.yaml
image: localhost:5000/newsbrief:dev-latest

# tekton/pipelines/ci-*.yaml
default: "localhost:5000"
```

### 3. Build and Push

```bash
# Build with Buildah (in Tekton)
buildah push localhost:5000/newsbrief:v0.7.5

# Or with Docker
docker build -t localhost:5000/newsbrief:v0.7.5 .
docker push localhost:5000/newsbrief:v0.7.5
```

## Consequences

### Positive
- ✅ Reliable image pulls from all namespaces
- ✅ No DNS resolution issues
- ✅ Standard pattern used by kind community
- ✅ Works with containerd's registry configuration
- ✅ Registry persists across cluster recreations

### Negative
- ⚠️ Requires Docker to run the registry container
- ⚠️ Registry runs outside Kubernetes (not managed by ArgoCD)
- ⚠️ Different setup than production (which would use a real registry)

### Neutral
- Registry data persists in Docker volume
- Need to ensure registry is running before cluster operations

## Migration

1. Delete existing in-cluster registry: `kubectl delete namespace registry`
2. Run setup script: `./scripts/setup-kind-registry.sh`
3. Update all image references to `localhost:5000`
4. Rebuild and push images
5. Restart deployments

## References

- [Kind Local Registry Documentation](https://kind.sigs.k8s.io/docs/user/local-registry/)
- [Containerd Registry Configuration](https://github.com/containerd/containerd/blob/main/docs/cri/registry.md)
- [ADR-0015: Local Kubernetes Distribution](0015-local-kubernetes-distribution.md)
