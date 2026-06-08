# ADR 0019: CI/CD Pipeline Design

## Status

**Superseded** by [ADR-0032: Cross-Platform CD Strategy](0032-cross-platform-cd-strategy.md) — June 2026

> The Tekton-specific pipeline design (Triggers, EventListener, smee.io relay) documented here has been replaced. GitHub Actions implements the equivalent stages (lint, test, build, scan, sign, deploy) via hosted runners. The pipeline structure and security gate principles remain valid and are reflected in the GitHub Actions workflow files.

## Context

With the adoption of Tekton (ADR-0016) and ArgoCD (ADR-0017), we need to define how our CI/CD pipelines will work, including:
- What triggers each pipeline
- What stages run for dev vs production
- How deployments are approved
- Security gates and image signing requirements

This ADR documents the pipeline design decisions that build upon the platform choices already made.

## Decision

### Pipeline Triggers and Environments

| Branch/Event | Pipeline | Deployment |
|--------------|----------|------------|
| PR to dev | PR Pipeline (lint + test only) | None |
| Merge to dev | Dev Pipeline (full CI) | Auto-deploy to dev |
| Merge to main | Prod Pipeline (full CI + signing) | Auto-deploy to prod |

**Key principle:** The merge to `main` serves as the approval gate for production. No separate manual approval step is needed - the PR review process is the approval.

### Trigger Implementation

**Decision:** Use Tekton Triggers with EventListener for webhook-based pipeline execution.

```
GitHub Push Event
       │
       ▼
┌──────────────────┐     ┌───────────────┐     ┌─────────────────┐     ┌─────────────┐
│  smee.io relay   │────▶│ EventListener │────▶│   Interceptor   │────▶│  Trigger    │
│  (local dev)     │     │               │     │ (GitHub filter) │     │  Template   │
└──────────────────┘     └───────────────┘     └─────────────────┘     └─────────────┘
                                                      │                       │
                                                      ▼                       ▼
                                               Validate webhook        Create PipelineRun
                                               signature + filter      (ci-dev or ci-prod)
                                               by branch
```

| Component | Role | Resource Location |
|-----------|------|-------------------|
| EventListener | HTTP endpoint receiving webhooks | `tekton/triggers/event-listener.yaml` |
| TriggerBinding | Extracts data (repo, branch, commit) from payload | `tekton/triggers/trigger-binding.yaml` |
| TriggerTemplate | Creates PipelineRun with extracted parameters | `tekton/triggers/trigger-template-*.yaml` |
| Interceptor | Validates signature, filters by branch | Built-in GitHub interceptor |

**Why Tekton Triggers:**

| Option | Considered | Decision |
|--------|------------|----------|
| Tekton Triggers | Native to Tekton, Kubernetes-native, event-driven | ✅ Chosen |
| GitHub Actions dispatch | Depends on GitHub, external to cluster | ❌ Rejected |
| External webhook handler | Additional component to maintain | ❌ Rejected |
| Manual pipeline runs | Defeats automation purpose | ❌ Rejected |

**Rationale:**
- **Native integration**: Tekton Triggers are part of the Tekton ecosystem
- **Self-contained**: Everything runs inside the cluster
- **Secure**: Validates webhook signatures using shared secret
- **Flexible**: CEL expressions for complex filtering (branch, event type)

**Local Development Strategy:**

For local development, GitHub cannot reach our cluster directly. We use smee.io as a webhook relay:

1. GitHub webhook → smee.io (public endpoint)
2. smee-client (local) → polls smee.io
3. smee-client → forwards to EventListener (localhost:8080)

**Trade-offs:**
- Requires running smee-client locally during development
- smee.io adds latency (~1-2 seconds)
- Alternative for production: Direct webhook endpoint via ingress

### Image Tagging Strategy

| Environment | Tag Format | Example |
|-------------|------------|---------|
| Development | `dev-latest` | `ghcr.io/deim0s13/newsbrief:dev-latest` |
| Production | Semantic version | `ghcr.io/deim0s13/newsbrief:v0.7.5` |

**Rationale:**
- Dev uses `dev-latest` for simplicity - always points to latest dev build
- Prod uses semantic versions for traceability and rollback capability
- SHA-based tags (`sha-abc1234`) retained for debugging/auditing

### Pipeline Stages

#### PR Pipeline (feature/* → dev)
```
┌─────────┐   ┌─────────┐
│  Lint   │──►│  Test   │
└─────────┘   └─────────┘
```
- Fast feedback on code quality
- No image build (saves time and resources)
- Must pass before merge allowed

#### Dev Pipeline (merge to dev)
```
┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌──────────────┐
│  Lint   │──►│  Test   │──►│  Build  │──►│  Scan   │──►│ Update k8s/  │
└─────────┘   └─────────┘   └─────────┘   └─────────┘   │ overlays/dev │
                                               │        └──────────────┘
                                               ▼                │
                                          Block on              ▼
                                          CRITICAL         ArgoCD Sync
                                          + Notify         (auto-deploy)
```

#### Prod Pipeline (merge to main)
```
┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌──────────────┐
│  Lint   │──►│  Test   │──►│  Build  │──►│  Scan   │──►│  Sign   │──►│ Update k8s/  │
└─────────┘   └─────────┘   └─────────┘   └─────────┘   └─────────┘   │ overlays/prod│
                                               │             │        └──────────────┘
                                               ▼             ▼                │
                                          Block on      Cosign +              ▼
                                          CRITICAL      SBOM              ArgoCD Sync
                                          + Notify                        (auto-deploy)
```

### Security Gates

| Gate | Dev Pipeline | Prod Pipeline |
|------|--------------|---------------|
| Trivy scan | Yes | Yes |
| Block on CRITICAL | Yes | Yes |
| Block on HIGH | No | Consider for future |
| Notification on block | Yes (console + future: Slack) | Yes |
| Image signing (Cosign) | No | Yes (required) |
| SBOM generation | No | Yes |
| Signed image required for deploy | No | Yes |

**Blocking behavior:**
- If Trivy finds CRITICAL vulnerabilities, pipeline fails
- Notification sent (initially via pipeline logs, future: webhook to Slack/Discord)
- Deployment does not proceed until vulnerabilities are addressed

### Container Build Strategy

**Decision:** Use Buildah in rootless mode for building container images.

| Option | Considered | Decision |
|--------|------------|----------|
| Kaniko | Daemonless, popular but no longer actively maintained | ❌ Rejected |
| Buildah (privileged) | Simple setup, but runs as root | ❌ Rejected |
| Buildah (rootless) | More secure, aligns with Podman ecosystem | ✅ Chosen |
| Docker-in-Docker | Requires Docker daemon, security concerns | ❌ Rejected |

**Why Buildah rootless:**
- **Security**: Runs without root privileges, reduces attack surface
- **Ecosystem alignment**: Part of the Podman/Buildah/Skopeo toolchain already in use
- **Actively maintained**: Supported by Red Hat, regular updates
- **OCI-compliant**: Produces standard container images compatible with any runtime
- **No daemon required**: Builds as a regular process, ideal for Kubernetes

**Configuration requirements:**
- Non-root security context in Tekton Task
- Storage driver: `vfs` (simple) or `overlay` with fuse-overlayfs (performant)
- User namespace mapping for rootless operation

### Container Registry Strategy

**Decision:** Deploy a local container registry inside the kind cluster.

```
┌─────────────────────────────────────────────────┐
│              kind cluster (newsbrief-dev)       │
│                                                 │
│  ┌──────────────┐      ┌────────────────────┐   │
│  │   Tekton     │ push │  Local Registry    │   │
│  │   Pipeline   │─────▶│  (registry:5000)   │   │
│  │              │      │                    │   │
│  │  ┌─────────┐ │      │  PVC: registry-    │   │
│  │  │ Buildah │ │      │       storage      │   │
│  │  └─────────┘ │      └────────────────────┘   │
│  └──────────────┘               │               │
│                           pull  │               │
│                                 ▼               │
│                        ┌─────────────────┐      │
│                        │   Application   │      │
│                        │   Deployments   │      │
│                        └─────────────────┘      │
└─────────────────────────────────────────────────┘
```

| Option | Considered | Decision |
|--------|------------|----------|
| kind load docker-image | Simple, but requires kind CLI in pipeline | ❌ Rejected |
| ghcr.io (GitHub) | Production-ready, but requires network/auth | ❌ Rejected (for local) |
| Local registry in cluster | Realistic, images persist, self-contained | ✅ Chosen |

**Why local registry:**
- **Realistic**: Mirrors production patterns (push/pull workflow)
- **Self-contained**: No external dependencies or network requirements
- **Persistent**: Images survive pipeline restarts via PVC
- **Portable**: Same approach works with any registry (swap URL for prod)

**Image naming convention:**
- Local development: `registry:5000/newsbrief:<tag>`
- Production (future): `ghcr.io/deim0s13/newsbrief:<tag>`

### Runtime Environment

All CI/CD runs locally:
- **Tekton**: Runs in local kind cluster (`newsbrief-dev`)
- **ArgoCD**: Runs in local kind cluster, manages deployments
- **Container Registry**: Local registry (`registry:5000`) inside cluster
- **Deployment Target**: Same local cluster (different namespaces for dev/prod)

**Rationale:** This is a learning/personal project. No cloud infrastructure needed. The same patterns would work in a cloud environment if needed later.

### Namespace Strategy

| Environment | Kubernetes Namespace | ArgoCD Application |
|-------------|---------------------|-------------------|
| Development | `newsbrief-dev` | `newsbrief-dev` |
| Production | `newsbrief-prod` | `newsbrief-prod` |

### GitOps Flow

1. Tekton pipeline builds image and pushes to registry
2. Pipeline updates image tag in `k8s/overlays/<env>/kustomization.yaml`
3. Commits change to Git
4. ArgoCD detects change and syncs to cluster
5. Deployment happens automatically

### Pipeline Workspace Strategy

**Decision:** Use `volumeClaimTemplate` for pipeline workspaces with a dedicated `git-clone` task.

**How it works:**
1. Pipeline starts → Tekton auto-creates a PVC (via volumeClaimTemplate)
2. `git-clone` task fetches source code into the workspace
3. Subsequent tasks (lint, test, build) share the same workspace
4. Pipeline completes → Tekton auto-deletes the PVC

**Why volumeClaimTemplate:**
| Approach | Considered | Decision |
|----------|------------|----------|
| Static PVC | Persists between runs, requires manual cleanup | ❌ Rejected |
| emptyDir | Simple but doesn't survive pod restarts | ❌ Rejected |
| volumeClaimTemplate | Auto-create/delete per pipeline run | ✅ Chosen |
| Clone in each task | No shared state needed | ❌ Rejected (wasteful) |

**Rationale:**
- Ephemeral by design - pipeline workspaces are temporary
- Self-managing - no manual PVC creation or cleanup scripts
- Isolated - each pipeline run gets a fresh workspace
- Standard Tekton pattern - well-documented, portable

**What ArgoCD manages vs. what Tekton manages:**
| Resource | Managed By | Reason |
|----------|------------|--------|
| Pipeline workspace PVCs | Tekton | Ephemeral, needed only during CI |
| Application PVCs (e.g., database) | ArgoCD | Persistent application state |
| Tekton Task/Pipeline definitions | ArgoCD | Part of infrastructure-as-code |
| TaskRuns/PipelineRuns | Tekton | Created on-demand per execution |

## Consequences

### Positive
- Clear separation between dev and prod pipelines
- Merge to main = production approval (leverages existing PR review process)
- Security gates prevent deploying vulnerable images
- Signed images provide supply chain integrity for production
- Everything runs locally - no cloud costs, fast iteration
- Buildah rootless provides secure, daemonless image builds
- Local registry mirrors production push/pull patterns
- Aligns with Podman ecosystem already in use

### Negative
- Local-only means no redundancy (laptop failure = CI/CD down)
- Dev-latest tag means no easy rollback in dev (acceptable for dev)
- Must remember to create proper version tag for prod releases
- Rootless Buildah requires more complex security context configuration
- Local registry adds another component to manage

### Risks
- CRITICAL vulnerability blocking could slow down urgent fixes
  - Mitigation: Document process for accepting specific CVEs when necessary
- Local registry availability depends on cluster being up
  - Mitigation: Can fall back to ghcr.io if needed
- Rootless builds may be slower than privileged builds
  - Mitigation: Acceptable tradeoff for security; optimize if needed later

## References

- [ADR-0016: CI/CD Platform Migration](0016-cicd-platform-migration.md)
- [ADR-0017: GitOps Tooling](0017-gitops-tooling.md)
- [ADR-0018: Secure Supply Chain](0018-secure-supply-chain.md)
