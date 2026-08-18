# Local Kubernetes Development Guide

This guide covers the local Kubernetes environment used for **production CD on macOS**: a `kind` cluster running ArgoCD, which watches this Git repo and auto-syncs the `dev` and `prod` overlays. There is no Tekton, in-cluster registry, or webhook relay in the current setup — CI runs entirely on GitHub Actions (see [CI-CD.md](CI-CD.md)); this cluster only does GitOps deployment.

> Windows does not run this stack at all — see [ADR-0032](../adr/0032-cross-platform-cd-strategy.md) for why Windows uses Podman Compose + GHCR polling instead.

## Architecture Overview

```
GitHub Actions (CI)
  builds, tests, scans, signs → pushes ghcr.io/deim0s13/newsbrief
  updates k8s/overlays/{dev,prod}/kustomization.yaml image tag
        │
        ▼
kind cluster "newsbrief-dev" (macOS)
  ┌───────────────────────────────────────────────────────────┐
  │                         ArgoCD                            │
  │   ┌─────────────────┐          ┌─────────────────┐        │
  │   │ newsbrief-dev    │          │ newsbrief-prod   │       │
  │   │ (watches dev)    │          │ (watches main)   │       │
  │   └────────┬─────────┘          └────────┬─────────┘       │
  │            ▼                             ▼                 │
  │   newsbrief-dev namespace         newsbrief-prod namespace │
  │   (localhost:8789)                (localhost:8788)         │
  └───────────────────────────────────────────────────────────┘
```

Despite the cluster's name (`newsbrief-dev`, a holdover from when it also ran CI), it hosts **both** the `newsbrief-dev` and `newsbrief-prod` namespaces/Applications.

## Prerequisites

| Tool | Purpose | Installation |
|------|---------|--------------|
| **Podman Desktop** | Container runtime (kind runs on the Podman provider) | [podman-desktop.io](https://podman-desktop.io) |
| **kind** | Local Kubernetes cluster | `brew install kind` |
| **kubectl** | Kubernetes CLI | `brew install kubectl` |
| **argocd** | ArgoCD CLI (optional — UI/`kubectl` also work) | `brew install argocd` |

```bash
podman --version
kind --version
kubectl version --client
argocd version --client
```

## Cluster Setup & Recovery

In normal use you don't run these steps by hand — `make infra-start` (or the launchd auto-start job) does all of it idempotently. This section explains what it does.

### One-time: auto-start install

```bash
make infra-autostart-install   # registers a launchd job that runs infra-start.sh on every login
make infra-autostart-status    # verify the launchd plist is loaded
```

### `make infra-start` (`scripts/infra-start.sh`)

1. Starts the Podman Compose prod stack (the Postgres DB the kind pods connect to via `host.containers.internal`)
2. Creates the `newsbrief-dev` kind cluster if it doesn't already exist (config: `k8s/kind/cluster-config.yaml`), otherwise starts the existing container
3. Exports kubeconfig (`kind export kubeconfig --name newsbrief-dev`)
4. Waits for the ArgoCD `argocd-server` Deployment to become available
5. **Re-applies `k8s/argocd/` Application CRs if missing** — cluster recreation wipes ArgoCD's own state, so this makes the script safe to re-run after a full cluster rebuild
6. Triggers an async sync for both `newsbrief-dev` and `newsbrief-prod` Applications
7. Re-establishes `kubectl port-forward`s for the prod app, dev app, and ArgoCD UI

### Manual recovery (Ansible)

For a fuller recovery after a reboot/sleep (also brings up Caddy, checks Ollama, etc.):

```bash
make recover     # runs ansible/playbooks/recover.yml
make status      # runs ansible/playbooks/status.yml
```

### Manual cluster teardown

```bash
kind delete cluster --name newsbrief-dev
```

## ArgoCD

### Access the UI

```bash
make argo-ui
# or: kubectl port-forward svc/argocd-server -n argocd 8443:443
```

Open `https://localhost:8443` (username `admin`; password via `kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d`).

### Applications

| Resource | Purpose | File |
|----------|---------|------|
| `AppProject` | Allowed repos/namespaces | `k8s/argocd/project.yaml` |
| `Application` (dev) | Watches `dev` branch → `newsbrief-dev` namespace | `k8s/argocd/app-dev.yaml` |
| `Application` (prod) | Watches `main` branch → `newsbrief-prod` namespace | `k8s/argocd/app-prod.yaml` |
| `ApplicationSet` | Alternative to the two `Application` files above (not currently active — both individual apps are used instead) | `k8s/argocd/appset.yaml` |

Auto-sync is enabled; ArgoCD polls Git every **5 minutes** (`timeout.reconciliation: 300s` in `k8s/argocd/argocd-cm.yaml`).

```bash
kubectl get applications -n argocd
kubectl describe application newsbrief-prod -n argocd
argocd app sync newsbrief-prod   # force an out-of-cycle sync
```

### Sync Waves

Resources deploy in order (lower numbers first; ArgoCD waits for each resource to be **healthy** before starting the next wave):

1. **Wave -1** — Namespace, and prod-only resources like the PVC
2. **Wave 0** — ConfigMap (`newsbrief-config`, including `DATABASE_URL`)
3. **Wave 1** — `Job` `newsbrief-db-migrate` — runs `alembic upgrade head` with the same image/env as the API pod. Uses an ArgoCD **Sync hook** with `hook-delete-policy: BeforeHookCreation` so each sync can replace the previous Job.
4. **Wave 2** — `Deployment newsbrief` — the API pods.
5. **PostSync (prod only)** — `Job newsbrief-embed-backfill` (`k8s/overlays/prod/embed-backfill-job.yaml`) — runs `python -m app.cli embed-backfill` after the Deployment is healthy, so rows still missing embeddings get backfilled on every prod sync. `activeDeadlineSeconds: 7200`; increase via overlay patch for a very large corpus.

**Plain `kubectl apply -k` does not respect sync waves** — resources may apply in arbitrary order with nothing waiting on the migration Job. Prefer ArgoCD for cluster deploys; if you must apply directly, apply the ConfigMap and Job first and `kubectl wait --for=condition=complete job/newsbrief-db-migrate -n <namespace>` before applying the rest.

## Kustomize Structure

```
k8s/
├── base/
│   ├── kustomization.yaml
│   ├── namespace.yaml
│   ├── configmap.yaml
│   ├── migrate-job.yaml       # Alembic `upgrade head` (ArgoCD Sync hook, wave 1)
│   ├── deployment.yaml
│   └── service.yaml
├── overlays/
│   ├── dev/
│   │   ├── kustomization.yaml # image tag updated by ci-dev.yml
│   │   └── deployment-patch.yaml
│   └── prod/
│       ├── kustomization.yaml # image tag updated by ci-prod.yml
│       ├── deployment-patch.yaml
│       ├── embed-backfill-job.yaml
│       └── pdb.yaml, pvc.yaml
├── infrastructure/
│   └── registry/              # legacy in-cluster registry manifests, no longer used by CI
└── argocd/
    ├── kustomization.yaml
    ├── project.yaml
    ├── app-dev.yaml, app-prod.yaml, appset.yaml
    ├── argocd-cm.yaml          # poll interval, UI config
    └── notifications-cm.yaml, notifications-secret.yaml
```

```bash
kubectl kustomize k8s/overlays/dev    # preview
kubectl kustomize k8s/overlays/prod
kubectl apply -k k8s/overlays/dev     # apply without ArgoCD (see sync-wave caveat above)
```

## Production Deployment Shape

`k8s/overlays/prod/deployment-patch.yaml` configures:
- 2 replicas with pod anti-affinity (spread across nodes)
- Rolling updates with `maxUnavailable: 0` (zero-downtime)
- `PodDisruptionBudget` ensuring at least 1 pod stays available
- Resource limits: 1Gi memory, 1 CPU

## Port Map

After `make infra-start` (or `make port-forwards`):

| Port | Target |
|------|--------|
| `localhost:8788` | `newsbrief-prod` namespace |
| `localhost:8789` | `newsbrief-dev` namespace |
| `localhost:8443` | ArgoCD UI |

## Troubleshooting

**ArgoCD Application missing after cluster recreation** — `make infra-start` re-applies `k8s/argocd/` automatically; if that didn't run, `kubectl apply -f k8s/argocd/`.

**Sync stuck / app shows `OutOfSync`** — check the migrate Job first (`kubectl get jobs -n <namespace>`, `kubectl logs job/newsbrief-db-migrate -n <namespace>`); a failed migration blocks the Deployment from wave 2.

**Port-forwards dropped after sleep** — `make port-forwards` re-establishes them (kills any stale ones first).

```bash
kubectl describe application newsbrief-prod -n argocd
kubectl get pods -n newsbrief-prod
kubectl logs -f deployment/newsbrief -n newsbrief-prod
```

## Related Documentation

- [ADR-0015: Local Kubernetes Distribution](../adr/0015-local-kubernetes-distribution.md) — why `kind`
- [ADR-0017: GitOps Tooling](../adr/0017-gitops-tooling.md) — why ArgoCD
- [ADR-0032: Cross-Platform CD Strategy](../adr/0032-cross-platform-cd-strategy.md) — why macOS and Windows differ, and why Tekton was dropped
- [CI-CD.md](CI-CD.md) — full CI/CD pipeline (GitHub Actions)
