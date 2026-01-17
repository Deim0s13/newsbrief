# Local Kubernetes Development Guide

This guide covers setting up a local Kubernetes environment for NewsBrief CI/CD development using kind, Tekton, and related tools.

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    kind cluster (newsbrief-dev)                 │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                   Tekton Pipelines                        │  │
│  │                                                           │  │
│  │  ┌─────────┐  ┌──────┐  ┌───────┐  ┌──────┐  ┌────────┐  │  │
│  │  │  lint   │  │ test │  │ build │  │ scan │  │  sign  │  │  │
│  │  └─────────┘  └──────┘  └───────┘  └──────┘  └────────┘  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                  │
│                              ▼                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Local Container Registry                     │  │
│  │                  (registry:5000)                          │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                  │
│                              ▼                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                      ArgoCD                               │  │
│  │                                                           │  │
│  │  ┌─────────────────┐      ┌─────────────────┐            │  │
│  │  │ newsbrief-dev   │      │ newsbrief-prod  │            │  │
│  │  │ (watches dev)   │      │ (watches main)  │            │  │
│  │  └────────┬────────┘      └────────┬────────┘            │  │
│  │           │                        │                      │  │
│  │           ▼                        ▼                      │  │
│  │  ┌─────────────────┐      ┌─────────────────┐            │  │
│  │  │ newsbrief-dev   │      │ newsbrief-prod  │            │  │
│  │  │   namespace     │      │   namespace     │            │  │
│  │  └─────────────────┘      └─────────────────┘            │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 📋 Prerequisites

### Required Tools

| Tool | Purpose | Installation |
|------|---------|--------------|
| **Docker/Podman** | Container runtime | [Docker Desktop](https://www.docker.com/products/docker-desktop/) or `brew install podman` |
| **kind** | Local Kubernetes clusters | `brew install kind` |
| **kubectl** | Kubernetes CLI | `brew install kubectl` |
| **tkn** | Tekton CLI | `brew install tektoncd-cli` |
| **argocd** | ArgoCD CLI | `brew install argocd` |
| **cosign** | Image signing | `brew install cosign` |

### Verify Installation

```bash
# Check all tools are installed
docker --version || podman --version
kind --version
kubectl version --client
tkn version
argocd version --client
cosign version
```

## 🚀 Cluster Setup

### 1. Create the Cluster

```bash
# Create kind cluster for NewsBrief development
kind create cluster --name newsbrief-dev

# Verify cluster is running
kubectl cluster-info --context kind-newsbrief-dev

# Set as default context
kubectl config use-context kind-newsbrief-dev
```

### 2. Install Tekton Pipelines

```bash
# Install Tekton Pipelines
kubectl apply --filename https://storage.googleapis.com/tekton-releases/pipeline/latest/release.yaml

# Wait for Tekton to be ready
kubectl wait --for=condition=ready pod -l app=tekton-pipelines-controller -n tekton-pipelines --timeout=120s

# Verify installation
tkn version
```

### 3. Install Tekton Tasks

```bash
# Install git-clone task from Tekton Hub
kubectl apply -f https://raw.githubusercontent.com/tektoncd/catalog/main/task/git-clone/0.9/git-clone.yaml

# Apply NewsBrief tasks
kubectl apply -f tekton/tasks/
```

### 4. Deploy Local Registry

```bash
# Deploy in-cluster registry
kubectl apply -k k8s/infrastructure/registry/

# Verify registry is running
kubectl get pods -n registry
kubectl get svc -n registry
```

### 5. Configure Cosign Signing Keys

```bash
# Generate key pair (one-time setup)
COSIGN_PASSWORD="your-secure-password" cosign generate-key-pair k8s://default/cosign-keys

# The public key is saved to cosign.pub
# Move to project for verification
mv cosign.pub k8s/secrets/

# Apply RBAC for Tekton to access keys
kubectl apply -f k8s/infrastructure/tekton-rbac.yaml
```

## 📦 Tekton Resources

### Tasks

| Task | Purpose | File |
|------|---------|------|
| `lint` | Code formatting (black + isort) | `tekton/tasks/lint.yaml` |
| `test` | pytest + mypy | `tekton/tasks/test.yaml` |
| `build-image` | Buildah rootless build | `tekton/tasks/build-image.yaml` |
| `security-scan` | Trivy vulnerability scan | `tekton/tasks/security-scan.yaml` |
| `sign-image` | Cosign signature | `tekton/tasks/sign-image.yaml` |
| `generate-sbom` | CycloneDX SBOM | `tekton/tasks/generate-sbom.yaml` |

### Pipelines

| Pipeline | Purpose | Trigger |
|----------|---------|---------|
| `ci-dev` | Development CI (lint, test, build, scan) | Merge to `dev` |
| `ci-prod` | Production CI (+ signing + SBOM) | Merge to `main` |

## 🏃 Running Pipelines

### Development Pipeline

```bash
# Run the dev pipeline
tkn pipeline start ci-dev \
  --workspace name=source,volumeClaimTemplateFile=tekton/pipelineruns/workspace-template.yaml \
  --param repo-url=https://github.com/Deim0s13/newsbrief.git \
  --param revision=dev \
  --param image-tag=dev-latest \
  --showlog
```

### Production Pipeline

```bash
# Run the prod pipeline with signing
tkn pipeline start ci-prod \
  --workspace name=source,volumeClaimTemplateFile=tekton/pipelineruns/workspace-template.yaml \
  --workspace name=sbom-output,volumeClaimTemplateFile=tekton/pipelineruns/workspace-template.yaml \
  --serviceaccount=tekton-pipeline \
  --param repo-url=https://github.com/Deim0s13/newsbrief.git \
  --param revision=main \
  --param image-tag=v0.7.5 \
  --showlog
```

### Running Individual Tasks

```bash
# Run lint task only
tkn task start lint \
  --workspace name=source,volumeClaimTemplateFile=tekton/pipelineruns/workspace-template.yaml \
  --showlog

# Run security scan on existing image
tkn task start security-scan \
  --param IMAGE=registry.registry:5000/newsbrief:dev-latest \
  --param SEVERITY=CRITICAL,HIGH \
  --param EXIT_ON_SEVERITY=CRITICAL \
  --param IGNORE_UNFIXED=true \
  --showlog
```

## 🔍 Monitoring & Debugging

### View Pipeline Runs

```bash
# List recent pipeline runs
tkn pipelinerun list

# View logs for a specific run
tkn pipelinerun logs <run-name>

# Describe a pipeline run
tkn pipelinerun describe <run-name>
```

### View Task Runs

```bash
# List recent task runs
tkn taskrun list

# View task run logs
tkn taskrun logs <run-name>
```

### Check Registry Contents

```bash
# List repositories in registry
kubectl run check-registry --rm -it --restart=Never --image=curlimages/curl -- \
  curl -s http://registry.registry:5000/v2/_catalog

# List tags for newsbrief image
kubectl run check-tags --rm -it --restart=Never --image=curlimages/curl -- \
  curl -s http://registry.registry:5000/v2/newsbrief/tags/list
```

### Debug Failed Runs

```bash
# Get detailed failure info
tkn pipelinerun describe <failed-run>

# Check pod events
kubectl describe pod <pod-name>

# View container logs
kubectl logs <pod-name> -c <step-name>
```

## 🧹 Cleanup

### Delete Pipeline Runs

```bash
# Delete all pipeline runs (keeps pipelines)
tkn pipelinerun delete --all

# Delete specific run
tkn pipelinerun delete <run-name>
```

### Delete Cluster

```bash
# Delete the entire kind cluster
kind delete cluster --name newsbrief-dev
```

### Clean Up PVCs

```bash
# List PVCs (workspace storage)
kubectl get pvc

# Delete old PVCs
kubectl delete pvc <pvc-name>
```

## 🔧 Troubleshooting

### Common Issues

**1. Tekton pods not starting**
```bash
# Check Tekton controller logs
kubectl logs -n tekton-pipelines -l app=tekton-pipelines-controller

# Verify resources
kubectl get all -n tekton-pipelines
```

**2. Registry not accessible**
```bash
# Check registry pod
kubectl get pods -n registry
kubectl logs -n registry <registry-pod>

# Test connectivity
kubectl run test-curl --rm -it --restart=Never --image=curlimages/curl -- \
  curl -v http://registry.registry:5000/v2/
```

**3. Cosign signing fails**
```bash
# Verify secret exists
kubectl get secret cosign-keys

# Check service account permissions
kubectl auth can-i get secrets --as=system:serviceaccount:default:tekton-pipeline
```

**4. Build fails with permission errors**
```bash
# Buildah rootless may need security context adjustments
# Check task definition for securityContext settings
kubectl get task build-image -o yaml | grep -A5 securityContext
```

## 🚀 ArgoCD GitOps

ArgoCD provides declarative GitOps continuous delivery. It watches Git repositories and automatically syncs changes to the cluster.

### Install ArgoCD

```bash
# Create namespace and install ArgoCD
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Wait for ArgoCD to be ready
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=argocd-server -n argocd --timeout=120s

# Install ArgoCD CLI
brew install argocd
```

### Get Admin Password

```bash
# Get initial admin password
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d && echo
```

### Access ArgoCD UI

```bash
# Port forward to access UI
kubectl port-forward svc/argocd-server -n argocd 8080:443

# Open in browser: https://localhost:8080
# Username: admin
# Password: (from command above)
```

### Deploy ArgoCD Applications

```bash
# Apply the NewsBrief ArgoCD project and applications
kubectl apply -k k8s/argocd/
```

### ArgoCD Resources

| Resource | Purpose | File |
|----------|---------|------|
| `AppProject` | Defines allowed repos and namespaces | `k8s/argocd/project.yaml` |
| `Application` (dev) | Watches `dev` branch, deploys to `newsbrief-dev` | `k8s/argocd/app-dev.yaml` |
| `Application` (prod) | Watches `main` branch, deploys to `newsbrief-prod` | `k8s/argocd/app-prod.yaml` |

### GitOps Workflow

```
┌──────────────────┐     ┌─────────────────┐     ┌────────────────────┐
│  Developer       │     │  Tekton CI      │     │  ArgoCD            │
│                  │     │                 │     │                    │
│  Push to dev ────┼────►│  Build & Push   │     │                    │
│                  │     │  Image          │     │                    │
│                  │     │       │         │     │                    │
│                  │     │       ▼         │     │                    │
│                  │     │  Update k8s/    │────►│  Detect change     │
│                  │     │  overlay tag    │     │       │            │
│                  │     └─────────────────┘     │       ▼            │
│                  │                             │  Sync to cluster   │
│                  │                             │       │            │
│                  │                             │       ▼            │
│                  │                             │  newsbrief-dev     │
│                  │                             │  namespace updated │
└──────────────────┘                             └────────────────────┘
```

### Monitor Applications

```bash
# List all ArgoCD applications
kubectl get applications -n argocd

# Check application status
kubectl describe application newsbrief-dev -n argocd

# View sync history
argocd app history newsbrief-dev
```

### Manual Sync (if needed)

```bash
# Sync via CLI
argocd app sync newsbrief-dev

# Or via kubectl
kubectl patch application newsbrief-dev -n argocd --type='merge' -p='{"operation":{"initiatedBy":{"username":"admin"},"sync":{}}}'
```

## 📦 Kustomize Structure

NewsBrief uses Kustomize for environment-specific configurations:

```
k8s/
├── base/                    # Base manifests
│   ├── kustomization.yaml
│   ├── namespace.yaml
│   ├── deployment.yaml
│   ├── service.yaml
│   └── configmap.yaml
├── overlays/
│   ├── dev/                 # Dev overrides
│   │   └── kustomization.yaml
│   └── prod/                # Prod overrides
│       └── kustomization.yaml
└── argocd/                  # ArgoCD applications
    ├── kustomization.yaml
    ├── project.yaml
    ├── app-dev.yaml
    └── app-prod.yaml
```

### Build and Preview

```bash
# Preview dev manifests
kubectl kustomize k8s/overlays/dev

# Preview prod manifests
kubectl kustomize k8s/overlays/prod

# Apply directly (without ArgoCD)
kubectl apply -k k8s/overlays/dev
```

## 📚 Related Documentation

- [ADR-0015: Local Kubernetes Distribution](../adr/0015-local-kubernetes-distribution.md) - Why kind
- [ADR-0016: CI/CD Platform Migration](../adr/0016-cicd-platform-migration.md) - Why Tekton
- [ADR-0017: GitOps Tooling](../adr/0017-gitops-tooling.md) - Why ArgoCD
- [ADR-0018: Secure Supply Chain](../adr/0018-secure-supply-chain.md) - Trivy, Cosign, SBOM
- [ADR-0019: CI/CD Pipeline Design](../adr/0019-cicd-pipeline-design.md) - Pipeline architecture
- [CI/CD Documentation](CI-CD.md) - Full CI/CD guide

## 🔜 Next Steps

After setting up ArgoCD:

1. **Phase 4**: Configure Tekton Triggers for automatic pipeline execution
2. **Phase 5**: Production deployment patterns
3. **Phase 6**: Advanced GitOps (ApplicationSets, progressive delivery)
