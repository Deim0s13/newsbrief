# ADR-0015: Local Kubernetes Distribution

## Status
**Accepted** - January 2026

## Context

As part of our GitOps learning journey (v0.7.5), we need a local Kubernetes cluster to run Tekton pipelines and ArgoCD. This cluster should closely mirror production Kubernetes while being lightweight enough for laptop development.

We're approaching this as a **modern startup** - cloud-native from day one, no legacy constraints.

### Requirements

1. **Lightweight** - Reasonable resource usage on MacBook
2. **Kubernetes-conformant** - Standard K8s APIs, not a subset
3. **Multi-node capable** - Can simulate production topology
4. **Registry support** - Local container registry for builds
5. **Easy setup/teardown** - Quick iteration during development
6. **Podman compatible** - Works with our existing container runtime

## Options Considered

### Option 1: kind (Kubernetes in Docker)

**What it is**: Runs Kubernetes nodes as containers (works with Podman too)

| Aspect | Details |
|--------|---------|
| **Resource usage** | ~500MB-1GB RAM per node |
| **Startup time** | ~30-60 seconds |
| **K8s conformance** | Full (used for K8s CI testing) |
| **Multi-node** | ✅ Yes |
| **Local registry** | ✅ Built-in support |
| **Podman support** | ✅ Native (`KIND_EXPERIMENTAL_PROVIDER=podman`) |
| **Ingress** | ✅ With extra config |
| **LoadBalancer** | Requires MetalLB or similar |

**Pros**:
- Official Kubernetes project (used to test K8s itself)
- Very stable and well-documented
- Works natively with Podman
- Excellent for CI/CD testing

**Cons**:
- Slightly more setup for ingress/load balancing
- No built-in dashboard

### Option 2: k3d (k3s in Docker)

**What it is**: Runs Rancher's k3s (lightweight K8s) in containers

| Aspect | Details |
|--------|---------|
| **Resource usage** | ~300-500MB RAM per node |
| **Startup time** | ~20-30 seconds |
| **K8s conformance** | Mostly (some features removed) |
| **Multi-node** | ✅ Yes |
| **Local registry** | ✅ Built-in `--registry-create` |
| **Podman support** | ⚠️ Experimental |
| **Ingress** | ✅ Traefik included |
| **LoadBalancer** | ✅ Built-in (servicelb) |

**Pros**:
- Lighter weight than kind
- Faster startup
- Ingress and LoadBalancer work out of box
- Great developer experience

**Cons**:
- Not 100% Kubernetes conformant (some APIs removed)
- Podman support is experimental
- Uses containerd, not our existing Podman images directly

### Option 3: minikube

**What it is**: Single or multi-node K8s cluster, multiple drivers

| Aspect | Details |
|--------|---------|
| **Resource usage** | ~2GB+ RAM (VM-based) |
| **Startup time** | ~2-5 minutes |
| **K8s conformance** | Full |
| **Multi-node** | ✅ Yes (recent versions) |
| **Local registry** | ✅ With addon |
| **Podman support** | ✅ Native driver |
| **Ingress** | ✅ With addon |
| **LoadBalancer** | ✅ `minikube tunnel` |

**Pros**:
- Most feature-rich (addons for everything)
- Native Podman driver
- Great for learning (lots of documentation)

**Cons**:
- Heaviest resource usage
- Slowest startup
- Originally designed for VMs (container mode newer)

### Comparison Matrix

| Criteria | kind | k3d | minikube | Weight |
|----------|------|-----|----------|--------|
| Resource efficiency | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | High |
| K8s conformance | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | High |
| Podman support | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ | High |
| Startup speed | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | Medium |
| Ease of setup | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | Medium |
| Production similarity | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | High |
| Community/docs | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | Medium |

## Decision

**We will use kind (Kubernetes in Docker)** with Podman as the container runtime.

### Rationale

1. **Full Kubernetes conformance** - What we learn applies directly to EKS/GKE/AKS
2. **Native Podman support** - Works with our existing tooling
3. **Used by Kubernetes project** - Battle-tested, stable, well-documented
4. **Right balance** - Not too heavy (minikube), not too stripped (k3s)
5. **Enterprise relevance** - Many teams use kind for local development

### Trade-offs Accepted

- Need to configure ingress separately (nginx-ingress or Contour)
- Need MetalLB or port-forwarding for LoadBalancer services
- Slightly more initial setup than k3d

## Implementation

### Cluster Configuration

```yaml
# kind/cluster-config.yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: newsbrief
nodes:
  - role: control-plane
    kubeadmConfigPatches:
      - |
        kind: InitConfiguration
        nodeRegistration:
          kubeletExtraArgs:
            node-labels: "ingress-ready=true"
    extraPortMappings:
      - containerPort: 80
        hostPort: 80
        protocol: TCP
      - containerPort: 443
        hostPort: 443
        protocol: TCP
  - role: worker
  - role: worker
containerdConfigPatches:
  - |-
    [plugins."io.containerd.grpc.v1.cri".registry.mirrors."localhost:5000"]
      endpoint = ["http://kind-registry:5000"]
```

### Setup Commands

```bash
# Create cluster with Podman
export KIND_EXPERIMENTAL_PROVIDER=podman
kind create cluster --config kind/cluster-config.yaml

# Verify
kubectl cluster-info
kubectl get nodes
```

### Makefile Targets

```makefile
k8s-up:       # Create local Kubernetes cluster
k8s-down:     # Delete cluster
k8s-status:   # Show cluster status
k8s-dashboard: # Open Kubernetes dashboard
```

## Consequences

### Positive
- Learn standard Kubernetes (not a variant)
- Skills transfer directly to cloud K8s
- Works with existing Podman setup
- Can test multi-node scenarios

### Negative
- More RAM usage than k3d (~1-2GB for 3-node cluster)
- Initial ingress/registry setup required
- Slightly longer startup than k3d

### Neutral
- Need to learn kind-specific configuration
- May need to revisit if Podman compatibility issues arise

## References

- [kind Quick Start](https://kind.sigs.k8s.io/docs/user/quick-start/)
- [kind with Podman](https://kind.sigs.k8s.io/docs/user/rootless/#creating-a-kind-cluster-with-podman)
- [Local Registry with kind](https://kind.sigs.k8s.io/docs/user/local-registry/)
- [Ingress with kind](https://kind.sigs.k8s.io/docs/user/ingress/)
