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
│  │                (kind-registry:5000)                       │  │
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

**Option A: Automatic via Bitwarden (Recommended)**

If you have Bitwarden CLI configured with the cosign keys stored:

```bash
# Unlock Bitwarden
export BW_SESSION=$(bw unlock --raw)

# Run recovery - automatically creates cosign-keys secret
make recover
```

**Option B: Manual Setup**

```bash
# Generate key pair (one-time setup)
cosign generate-key-pair

# Create K8s secret with the keys
kubectl create secret generic cosign-keys \
  --from-file=cosign.key=cosign.key \
  --from-file=cosign.pub=cosign.pub \
  --from-literal=cosign.password='your-password' \
  -n default

# Copy public key to repo
cp cosign.pub k8s/secrets/

# Apply RBAC for Tekton to access keys
kubectl apply -f k8s/infrastructure/tekton-rbac.yaml
```

**Bitwarden Storage:**
- Store `cosign.key` contents in a Secure Note named `newsbrief-cosign-key`
- Store the password in a Login named `newsbrief-cosign-password`

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

### Development pipeline from the host (reliable)

Webhooks depend on Smee + port-forward. To run the same **`ci-dev`** workload after you push without that chain:

```bash
# From repo root: push dev to GitHub, then start ci-dev on the cluster
make push-dev

# Only start ci-dev (e.g. re-run after fixing cluster)
make ci-dev
```

`SKIP_CI_DEV=1 make push-dev` pushes without starting the pipeline.

### Development Pipeline

```bash
# Run the dev pipeline (from repo root so the workspace template path resolves)
# ci-dev only declares repo-url + revision; it requires a `source` workspace — without
# --workspace, tkn prompts interactively.
tkn pipeline start ci-dev -n default \
  --workspace name=source,volumeClaimTemplateFile=tekton/pipelineruns/workspace-template.yaml \
  --param repo-url=https://github.com/Deim0s13/newsbrief.git \
  --param revision=dev \
  --showlog
```

### Production Pipeline

```bash
# Run the prod pipeline with signing (release version = pyproject [project].version on `revision`)
tkn pipeline start ci-prod \
  --workspace name=source,volumeClaimTemplateFile=tekton/pipelineruns/workspace-template.yaml \
  --workspace name=sbom-output,volumeClaimTemplateFile=tekton/pipelineruns/workspace-template.yaml \
  --serviceaccount=tekton-pipeline \
  --param repo-url=https://github.com/Deim0s13/newsbrief.git \
  --param revision=main \
  --param build-tag=latest \
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
  --param IMAGE=localhost:5001/newsbrief:dev-latest \
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
  curl -s http://localhost:5001/v2/_catalog

# List tags for newsbrief image
kubectl run check-tags --rm -it --restart=Never --image=curlimages/curl -- \
  curl -s http://localhost:5001/v2/newsbrief/tags/list
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
  curl -v http://localhost:5001/v2/
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

Use a **local port other than 8080** if you run the Tekton EventListener relay (`make webhook-relay-start` uses **localhost:8080**).

```bash
# Port forward (example: host 8443 → server 443)
kubectl port-forward svc/argocd-server -n argocd 8443:443

# Open in browser: https://localhost:8443
# Username: admin
# Password: (from command above)
```

Or run **`make argo-ui`** (same port-forward, see Makefile).

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
│   ├── configmap.yaml
│   ├── migrate-job.yaml     # Alembic `upgrade head` (Argo CD Sync hook, wave 1)
│   ├── deployment.yaml
│   └── service.yaml
├── overlays/
│   ├── dev/                 # Dev overrides
│   │   └── kustomization.yaml
│   └── prod/                # Prod overrides
│       ├── kustomization.yaml
│       ├── embed-backfill-job.yaml  # `embed-backfill` CLI (PostSync hook; #254)
│       ├── deployment-patch.yaml
│       └── …
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

## ⚡ Tekton Triggers

Tekton Triggers enables automatic pipeline execution when GitHub events occur.

### Install Tekton Triggers

```bash
# Install Tekton Triggers
kubectl apply --filename https://storage.googleapis.com/tekton-releases/triggers/latest/release.yaml

# Wait for readiness
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=webhook -n tekton-pipelines --timeout=60s

# Install interceptors (GitHub, CEL, etc.)
kubectl apply --filename https://storage.googleapis.com/tekton-releases/triggers/latest/interceptors.yaml
```

### Deploy Triggers

```bash
# Create webhook secret (generate a strong random token)
WEBHOOK_SECRET=$(openssl rand -hex 20)
kubectl create secret generic github-webhook-secret --from-literal=token=$WEBHOOK_SECRET
echo "Save this secret for GitHub webhook config: $WEBHOOK_SECRET"

# Deploy trigger resources
kubectl apply -k tekton/triggers/
```

### Trigger Architecture

```
GitHub Push ──► smee.io ──► EventListener ──► Interceptor ──► TriggerTemplate ──► PipelineRun
     │                           │                  │                                  │
     │                           │                  │                                  │
     ▼                           ▼                  ▼                                  ▼
  Webhook                  Validates          Filters by          Creates ci-dev or
  Payload                  Signature          Branch              ci-prod pipeline
```

### Trigger Resources

| Resource | Purpose | File |
|----------|---------|------|
| `TriggerBinding` | Extracts repo, branch, commit from webhook | `tekton/triggers/trigger-binding.yaml` |
| `TriggerTemplate` (dev) | Creates ci-dev PipelineRun | `tekton/triggers/trigger-template-dev.yaml` |
| `TriggerTemplate` (prod) | Creates ci-prod PipelineRun | `tekton/triggers/trigger-template-prod.yaml` |
| `EventListener` | Receives webhooks, routes to triggers | `tekton/triggers/event-listener.yaml` |

### Webhook Relay with smee.io

For local development, use smee.io to relay GitHub webhooks.

**Recommended (one command — prod/dev/EL/dashboard forwards + Smee):**

```bash
make port-forwards
make webhook-relay-status   # optional
# make webhook-relay-stop   # stops Smee only; pkill kubectl port-forward to stop forwards
```

(`make webhook-relay-start` is an alias for `make port-forwards`.)

**Manual (two terminals):**

```bash
# Terminal 1: Port-forward EventListener
kubectl port-forward svc/el-newsbrief-listener 8080:8080 -n default

# Terminal 2: Run smee client
./scripts/smee-client.sh
# Or directly:
npx smee-client --url https://smee.io/cddqBCYHwHG3ZcUY --target http://localhost:8080
```

### Configure GitHub Webhook

1. Go to: `https://github.com/Deim0s13/newsbrief/settings/hooks`
2. Add webhook:
   - **Payload URL**: `https://smee.io/cddqBCYHwHG3ZcUY`
   - **Content type**: `application/json`
   - **Secret**: Your webhook secret (from `kubectl get secret github-webhook-secret`)
   - **Events**: Just the push event

### Test Triggers Manually

```bash
# Get webhook secret
SECRET=$(kubectl get secret github-webhook-secret -o jsonpath='{.data.token}' | base64 -d)

# Create signed test webhook
PAYLOAD='{"ref":"refs/heads/dev","after":"HEAD","repository":{"clone_url":"https://github.com/Deim0s13/newsbrief.git"},"head_commit":{"message":"Test","author":{"name":"Tester"}}}'
SIGNATURE="sha256=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $2}')"

# Send webhook
curl -X POST http://localhost:8080 \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: push" \
  -H "X-Hub-Signature-256: $SIGNATURE" \
  -d "$PAYLOAD"

# Check PipelineRun was created
kubectl get pipelineruns --sort-by=.metadata.creationTimestamp | tail -3
```

### Monitor Triggers

```bash
# Check EventListener status
kubectl get eventlistener newsbrief-listener

# View EventListener logs
kubectl logs -l eventlistener=newsbrief-listener -f

# List triggered PipelineRuns
kubectl get pipelineruns -l triggers.tekton.dev/trigger=github-push
```

## 🏭 Production Patterns (Phase 5)

### Resource Limits and Scaling

Production deployments include:
- **2 replicas** with pod anti-affinity for HA
- **Rolling updates** with zero downtime (`maxUnavailable: 0`)
- **PodDisruptionBudget** ensuring at least 1 pod available
- **Resource limits**: 1Gi memory, 1 CPU

```yaml
# k8s/overlays/prod/deployment-patch.yaml
spec:
  replicas: 2
  strategy:
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  template:
    spec:
      affinity:
        podAntiAffinity:  # Spread across nodes
          preferredDuringSchedulingIgnoredDuringExecution: ...
```

### Image Promotion Workflow

**Dev (`newsbrief-dev`):** Tekton **`ci-dev`** only runs **lint + test** (no image build). To refresh the image Argo deploys, from repo root run **`make push-kind-dev-image`** (builds current tree, pushes **`localhost:5000/newsbrief:dev-latest`** → Kind registry; Git overlay expects **`dev-latest`**).

```
dev branch + make push-kind-dev-image ──► kind-registry:5000/newsbrief:dev-latest
                                        │
                                        ▼
                              ArgoCD syncs to newsbrief-dev
                                        │
                    ┌───────────────────┴────────────────────┐
                    │                                        │
                    ▼                                        ▼
main branch ──► Tekton builds ──► kind-registry:5000/newsbrief:v0.7.x
                                        │
                                        ▼
                              ArgoCD syncs to newsbrief-prod
```

### Sync Waves

Resources deploy in order using Argo CD sync waves (lower numbers first; Argo CD waits for a resource to be **healthy** before moving to the next wave—so the migrate `Job` must finish successfully before the `Deployment` rolls):

1. **Wave -1**: Namespace (and prod-only resources such as PVC that use wave -1)
2. **Wave 0**: ConfigMaps (e.g. `newsbrief-config` including `DATABASE_URL`)
3. **Wave 1**: **`Job` `newsbrief-db-migrate`** — runs `alembic upgrade head` using the same image and `envFrom` as the API pod. The Job uses Argo **Sync** hook + **`hook-delete-policy: BeforeHookCreation`** so a new Job can replace the old one (plain `Replace=true` breaks Job validation on many clusters).

4. **Wave 2**: **`Deployment` `newsbrief`** — API pods (same ordering as before).

5. **PostSync (wave 3, prod only)**: **`Job` `newsbrief-embed-backfill`** (`k8s/overlays/prod/embed-backfill-job.yaml`) — runs `python -m app.cli embed-backfill` with production `DATABASE_URL`, `OLLAMA_BASE_URL`, and embedding settings from **`newsbrief-config`**. Runs **after** the Deployment is healthy so each **newsbrief-prod** sync backfills rows still missing vectors (re-sync with nothing to do exits quickly). **Dev** overlay does not include this Job; use the CLI locally with `--dev` if you need the same behavior. Tuned with **`activeDeadlineSeconds: 7200`**; increase via overlay patch if a large corpus needs longer. A failing Job fails the Argo sync hook so the operator sees it. Tekton **`ci-prod`** does not run backfill directly; it relies on this hook after **`update-manifest`** triggers Argo.

**Plain `kubectl apply -k`**: Kubernetes does not interpret Argo sync waves; resources may be applied in an arbitrary order and nothing waits for the Job before starting pods. Prefer Argo CD for cluster deploys, or run migrations explicitly first (apply ConfigMap and Job, `kubectl wait --for=condition=complete job/newsbrief-db-migrate -n <namespace>`, then apply the rest).

## 🚀 Advanced GitOps (Phase 6)

### ApplicationSets

ApplicationSets manage multiple environments from a single template:

```yaml
# k8s/argocd/appset.yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
spec:
  generators:
    - list:
        elements:
          - env: dev
            branch: dev
          - env: prod
            branch: main
  template:
    spec:
      source:
        path: 'k8s/overlays/{{env}}'
        targetRevision: '{{branch}}'
```

**Enable ApplicationSet** (replaces individual apps):
```bash
# Edit k8s/argocd/kustomization.yaml
# Comment out app-dev.yaml and app-prod.yaml
# Uncomment appset.yaml
kubectl apply -k k8s/argocd/
```

### ArgoCD Notifications

Notifications are configured to alert on:
- ✅ Successful deployments
- ❌ Sync failures
- ⚠️ Health degradation

```bash
# View notification logs
kubectl logs -n argocd -l app.kubernetes.io/name=argocd-notifications-controller

# Test notifications by triggering a sync
argocd app sync newsbrief-dev
```

**Configure Slack/Webhook** (when ready):
```bash
# Edit k8s/argocd/notifications-secret.yaml
# Add your Slack token or webhook URL
kubectl apply -f k8s/argocd/notifications-secret.yaml
```

## 🔄 Environment Recovery

After a laptop reboot or when the environment needs to be restored, use the Ansible recovery playbook:

### Quick Recovery

```bash
# Full environment recovery (recommended)
make recover

# With Bitwarden for automatic cosign secret creation
export BW_SESSION=$(bw unlock --raw)
make recover
```

### What `make recover` Does

1. **Starts Podman** - Container runtime
2. **Creates Kind cluster** - If not already running
3. **Installs Tekton** - Pipelines, Triggers, Dashboard
4. **Installs ArgoCD** - GitOps controller
5. **Creates secrets** - Cosign keys from Bitwarden (if BW_SESSION set)
6. **Starts port forwards** - Prod app, Tekton dashboard
7. **Starts Caddy** - Reverse proxy for HTTPS
8. **Starts Smee** - GitHub webhook relay

### Check Status

```bash
# View current environment status
make status

# Or run the status playbook directly
ansible-playbook -i ansible/inventory/localhost.yml ansible/playbooks/status.yml
```

### Manual Service Start

If you need to start individual services:

```bash
# Port forwards
kubectl port-forward svc/newsbrief -n newsbrief-prod 8788:8787 &
kubectl port-forward svc/el-newsbrief-listener 8080:8080 &
kubectl port-forward svc/tekton-dashboard -n tekton-pipelines 9097:9097 &

# Smee webhook relay
npx smee-client --url "https://smee.io/cddqBCYHwHG3ZcUY" --target "http://localhost:8080" &

# Caddy (if not using launchd)
cd caddy-data && caddy run --config ../Caddyfile &
```

## 📚 Related Documentation

- [ADR-0015: Local Kubernetes Distribution](../adr/0015-local-kubernetes-distribution.md) - Why kind
- [ADR-0016: CI/CD Platform Migration](../adr/0016-cicd-platform-migration.md) - Why Tekton
- [ADR-0017: GitOps Tooling](../adr/0017-gitops-tooling.md) - Why ArgoCD
- [ADR-0018: Secure Supply Chain](../adr/0018-secure-supply-chain.md) - Trivy, Cosign, SBOM
- [ADR-0019: CI/CD Pipeline Design](../adr/0019-cicd-pipeline-design.md) - Pipeline architecture
- [CI/CD Documentation](CI-CD.md) - Full CI/CD guide

## ✅ Setup Complete

The full GitOps stack is now configured:

| Component | Purpose | Status |
|-----------|---------|--------|
| kind | Local Kubernetes cluster | ✅ |
| Tekton Pipelines | CI/CD execution | ✅ |
| Tekton Triggers | Automatic pipeline triggering | ✅ |
| ArgoCD | GitOps deployment | ✅ |
| Local Registry | Image storage | ✅ |
| Cosign | Image signing | ✅ |
| Trivy | Security scanning | ✅ |

**To activate full automation:**
1. Configure GitHub webhook with smee.io relay
2. Push to `dev` → triggers ci-dev → ArgoCD deploys to newsbrief-dev
3. Merge to `main` → triggers ci-prod → ArgoCD deploys to newsbrief-prod
