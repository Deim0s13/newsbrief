# ADR-0017: GitOps Tooling

## Status
**Accepted** - January 2026

## Context

GitOps is a paradigm where Git is the single source of truth for declarative infrastructure and applications. Changes are made via Git commits, and an operator reconciles the cluster state to match Git.

We need to choose a GitOps tool to manage NewsBrief deployments on our Kubernetes cluster.

### GitOps Principles

1. **Declarative** - System state described declaratively
2. **Versioned** - Desired state stored in Git
3. **Automated** - Changes automatically applied
4. **Auditable** - Git history = deployment history

## Options Considered

### Option 1: ArgoCD

**What it is**: Declarative GitOps CD tool for Kubernetes (Argo Project / CNCF)

| Aspect | Details |
|--------|---------|
| **Architecture** | Controller + API Server + UI |
| **Sync approach** | Pull-based (controller polls Git) |
| **UI** | ✅ Rich web UI with visualizations |
| **Multi-cluster** | ✅ Native support |
| **Helm support** | ✅ Native |
| **Kustomize support** | ✅ Native |
| **RBAC** | ✅ Fine-grained |
| **Resource usage** | ~500MB-1GB RAM |

**Pros**:
- Excellent web UI for visualizing deployments
- Strong multi-cluster support
- Large community, lots of documentation
- Part of CNCF (graduated project)
- Used by: Intuit, Tesla, IBM, Red Hat

**Cons**:
- Heavier resource usage
- More complex architecture
- UI can be overwhelming initially

### Option 2: Flux

**What it is**: GitOps toolkit for Kubernetes (Weaveworks / CNCF)

| Aspect | Details |
|--------|---------|
| **Architecture** | Set of controllers (modular) |
| **Sync approach** | Pull-based (controllers poll Git) |
| **UI** | ⚠️ Basic (Weave GitOps UI optional) |
| **Multi-cluster** | ✅ Via Flux + cluster API |
| **Helm support** | ✅ Native (HelmRelease CRD) |
| **Kustomize support** | ✅ Native (Kustomization CRD) |
| **RBAC** | ✅ Kubernetes-native |
| **Resource usage** | ~200-400MB RAM |

**Pros**:
- Lighter weight than ArgoCD
- More modular (use only what you need)
- Tighter Helm integration
- Kubernetes-native approach

**Cons**:
- Weaker UI (CLI-focused)
- Steeper learning curve for beginners
- Less visual feedback

### Option 3: Jenkins X

**What it is**: CI/CD solution for Kubernetes (includes GitOps)

| Aspect | Details |
|--------|---------|
| **Architecture** | Full CI/CD platform |
| **Sync approach** | Push + Pull |
| **UI** | ✅ Web UI |
| **Focus** | CI/CD + GitOps combined |

**Pros**:
- All-in-one solution
- Good for teams new to Kubernetes

**Cons**:
- Very heavy (includes full CI)
- We already chose Tekton for CI
- Overkill for our needs

### Comparison Matrix

| Criteria | ArgoCD | Flux | Jenkins X | Weight |
|----------|--------|------|-----------|--------|
| Web UI quality | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | High |
| Learning curve | ⭐⭐⭐ | ⭐⭐ | ⭐⭐ | Medium |
| Resource usage | ⭐⭐ | ⭐⭐⭐⭐ | ⭐ | Medium |
| Visualization | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | High |
| Community/docs | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | Medium |
| Enterprise adoption | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | Medium |
| Standalone CD | ✅ | ✅ | ❌ | High |

## Decision

**We will use ArgoCD** for GitOps continuous delivery.

### Rationale

1. **Visual learning** - Web UI helps understand what's happening
2. **Enterprise adoption** - Widely used, skills transfer to jobs
3. **Excellent documentation** - Great for learning
4. **Clear separation** - Tekton for CI, ArgoCD for CD
5. **Application-centric** - Designed around applications, not just manifests

### Trade-offs Accepted

- Higher resource usage than Flux (~500MB-1GB)
- More components to understand initially
- UI can be overwhelming at first

## Implementation

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Git Repository                        │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ k8s/                                                 │    │
│  │ ├── base/           # Base manifests                │    │
│  │ │   ├── deployment.yaml                             │    │
│  │ │   ├── service.yaml                                │    │
│  │ │   └── kustomization.yaml                          │    │
│  │ └── overlays/                                       │    │
│  │     ├── dev/        # Dev-specific patches          │    │
│  │     ├── staging/    # Staging config                │    │
│  │     └── prod/       # Production config             │    │
│  └─────────────────────────────────────────────────────┘    │
└──────────────────────────┬──────────────────────────────────┘
                           │ polls
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                     ArgoCD (in cluster)                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │   Repo       │  │  Application │  │    Sync      │       │
│  │   Server     │──│  Controller  │──│   Engine     │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
│                            │                                 │
│                            ▼                                 │
│                    ┌──────────────┐                         │
│                    │   ArgoCD     │ ◀── User access         │
│                    │     UI       │     (port 8080)         │
│                    └──────────────┘                         │
└──────────────────────────┬──────────────────────────────────┘
                           │ deploys
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                 Kubernetes Namespace                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │   newsbrief │  │  postgres   │  │   caddy     │          │
│  │     pod     │  │     pod     │  │     pod     │          │
│  └─────────────┘  └─────────────┘  └─────────────┘          │
└─────────────────────────────────────────────────────────────┘
```

### Directory Structure

```
k8s/
├── base/
│   ├── kustomization.yaml
│   ├── namespace.yaml
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── configmap.yaml
│   ├── secret.yaml          # Sealed/encrypted
│   └── ingress.yaml
└── overlays/
    ├── dev/
    │   ├── kustomization.yaml
    │   ├── patch-replicas.yaml    # replicas: 1
    │   ├── patch-resources.yaml   # lower limits
    │   └── patch-image.yaml       # :dev tag
    ├── staging/
    │   ├── kustomization.yaml
    │   ├── patch-replicas.yaml    # replicas: 2
    │   └── patch-image.yaml       # :staging tag
    └── prod/
        ├── kustomization.yaml
        ├── patch-replicas.yaml    # replicas: 3
        ├── patch-resources.yaml   # higher limits
        └── patch-image.yaml       # :v0.7.5 tag

argocd/
├── dev-app.yaml          # ArgoCD Application for dev
├── staging-app.yaml      # ArgoCD Application for staging
└── prod-app.yaml         # ArgoCD Application for prod
```

### ArgoCD Application Definition

```yaml
# argocd/dev-app.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: newsbrief-dev
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/Deim0s13/newsbrief.git
    targetRevision: dev
    path: k8s/overlays/dev
  destination:
    server: https://kubernetes.default.svc
    namespace: newsbrief-dev
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

### Makefile Targets

```makefile
# ArgoCD Commands
argocd-install:   # Install ArgoCD on cluster
argocd-ui:        # Open ArgoCD web UI
argocd-login:     # CLI login to ArgoCD
argocd-sync:      # Force sync application
argocd-status:    # Show application status
```

### Sync Workflow

1. Developer pushes to `dev` branch
2. Tekton pipeline builds and pushes image with new tag
3. Tekton updates image tag in `k8s/overlays/dev/patch-image.yaml`
4. ArgoCD detects Git change (polls every 3 minutes)
5. ArgoCD syncs: applies updated manifests
6. New pod rolls out with new image

## Consequences

### Positive
- Visual feedback on deployments
- Easy rollback via Git revert
- Audit trail in Git history
- Learn industry-standard GitOps tool

### Negative
- Additional ~500MB-1GB RAM usage
- More components to understand
- Need to learn Kustomize

### Neutral
- Polling-based (3 min delay by default)
- Can configure webhooks for faster sync

## References

- [ArgoCD Documentation](https://argo-cd.readthedocs.io/)
- [ArgoCD Getting Started](https://argo-cd.readthedocs.io/en/stable/getting_started/)
- [GitOps Principles](https://opengitops.dev/)
- [Kustomize Documentation](https://kustomize.io/)
