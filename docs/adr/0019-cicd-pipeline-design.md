# ADR 0019: CI/CD Pipeline Design

## Status

Accepted

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

### Runtime Environment

All CI/CD runs locally:
- **Tekton**: Runs in local kind cluster (`newsbrief-dev`)
- **ArgoCD**: Runs in local kind cluster, manages deployments
- **Container Registry**: Local registry or ghcr.io
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

## Consequences

### Positive
- Clear separation between dev and prod pipelines
- Merge to main = production approval (leverages existing PR review process)
- Security gates prevent deploying vulnerable images
- Signed images provide supply chain integrity for production
- Everything runs locally - no cloud costs, fast iteration

### Negative
- Local-only means no redundancy (laptop failure = CI/CD down)
- Dev-latest tag means no easy rollback in dev (acceptable for dev)
- Must remember to create proper version tag for prod releases

### Risks
- CRITICAL vulnerability blocking could slow down urgent fixes
  - Mitigation: Document process for accepting specific CVEs when necessary
- Local registry availability depends on laptop being on
  - Mitigation: Can fall back to ghcr.io if needed

## References

- [ADR-0016: CI/CD Platform Migration](0016-cicd-platform-migration.md)
- [ADR-0017: GitOps Tooling](0017-gitops-tooling.md)
- [ADR-0018: Secure Supply Chain](0018-secure-supply-chain.md)
