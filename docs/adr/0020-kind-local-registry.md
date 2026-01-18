# ADR-0020: Kind Local Registry Configuration

**Status**: Accepted
**Date**: 2026-01-18
**Deciders**: Development Team

## Context

NewsBrief uses a local Kubernetes cluster (kind) for development and CI/CD. Container images are built by Tekton pipelines and stored in an in-cluster registry. However, kind nodes cannot pull images from an in-cluster registry by default because:

1. **DNS Resolution**: Kind nodes use the host's DNS, not cluster DNS (CoreDNS)
2. **TLS Requirements**: Containerd defaults to HTTPS for registries
3. **Network Isolation**: Kind nodes run in Docker, isolated from cluster networking

This causes `ImagePullBackOff` errors when ArgoCD tries to deploy applications.

## Decision

Implement the **kind local registry** pattern as documented in the [kind documentation](https://kind.sigs.k8s.io/docs/user/local-registry/):

1. Run registry as a Docker container on host network (not in-cluster)
2. Connect registry to kind's Docker network
3. Configure kind nodes to recognize `localhost:5000` as insecure registry
4. Use `localhost:5000` as the image reference in all manifests

## Alternatives Considered

### Option 1: In-Cluster Registry with FQDN
- **Approach**: Deploy registry in cluster, use `registry.registry.svc.cluster.local:5000`
- **Rejected**: Kind nodes can't resolve cluster DNS; requires complex containerd configuration

### Option 2: External Registry (Docker Hub, GHCR)
- **Approach**: Push images to external registry
- **Rejected**: Violates privacy-first principle; requires internet for local development

### Option 3: kind Local Registry (Selected)
- **Approach**: Registry runs alongside kind in Docker, connected via shared network
- **Selected**: Native kind support, no DNS issues, works offline

## Implementation

### Registry Setup Script

```bash
#!/bin/bash
# scripts/setup-kind-registry.sh

REGISTRY_NAME="kind-registry"
REGISTRY_PORT="5000"
KIND_CLUSTER_NAME="newsbrief-dev"

# Create registry container if not exists
if [ "$(docker inspect -f '{{.State.Running}}' "${REGISTRY_NAME}" 2>/dev/null)" != 'true' ]; then
  docker run -d --restart=always -p "127.0.0.1:${REGISTRY_PORT}:5000" \
    --network bridge --name "${REGISTRY_NAME}" registry:2
fi

# Connect registry to kind network
if [ "$(docker inspect -f='{{json .NetworkSettings.Networks.kind}}' "${REGISTRY_NAME}")" = 'null' ]; then
  docker network connect "kind" "${REGISTRY_NAME}"
fi
```

### Kind Cluster Configuration

```yaml
# kind/cluster-config.yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: newsbrief-dev
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
```

### Registry ConfigMap for Cluster

```yaml
# Applied after cluster creation
apiVersion: v1
kind: ConfigMap
metadata:
  name: local-registry-hosting
  namespace: kube-public
data:
  localRegistryHosting.v1: |
    host: "localhost:5000"
    help: "https://kind.sigs.k8s.io/docs/user/local-registry/"
```

### Image References

All manifests use `localhost:5000/newsbrief:tag`:

```yaml
# k8s/base/deployment.yaml
image: localhost:5000/newsbrief:dev-latest
```

## Consequences

### Positive
- ✅ Native kind support with documented pattern
- ✅ No DNS resolution issues
- ✅ Works completely offline
- ✅ Fast image pulls (local network)
- ✅ Simple `docker push localhost:5000/image` workflow

### Negative
- ⚠️ Registry persists outside cluster (Docker container)
- ⚠️ Requires setup script before cluster creation
- ⚠️ `localhost:5000` only works on development machine

### Neutral
- Registry data persists in Docker volume (survives cluster recreation)
- Same pattern used by many kind users

## References

- [kind Local Registry Documentation](https://kind.sigs.k8s.io/docs/user/local-registry/)
- [Kubernetes Local Registry Hosting KEP](https://github.com/kubernetes/enhancements/tree/master/keps/sig-cluster-lifecycle/generic/1755-communicating-a-local-registry)
