# ADR-0032: Cross-Platform Continuous Delivery Strategy

## Status
**Accepted** — June 2026

## Context

NewsBrief runs on two personal machines — a macOS MBP and a Windows laptop (WSL2). CI is handled by GitHub Actions and already delivers a verified, signed image to GHCR on every merge. The missing piece is the **CD leg**: neither machine was automatically picking up new versions without a manual `make` command after CI completed.

### What "done" looks like

- A PR merges to `main`
- GitHub Actions builds, tests, and pushes `ghcr.io/deim0s13/newsbrief:latest` to GHCR
- **Both machines deploy the new version automatically**, including when a machine has been offline for days and comes back online

### Constraints

| Constraint | Detail |
|---|---|
| No cloud infrastructure | Both machines are personal laptops; no always-on server |
| kind + WSL2 rootless Podman is unreliable | The kind cluster state does not survive WSL2 restarts; kubeconfig is not reliably exported |
| macOS kind/ArgoCD has deployed successfully | The GitOps path works on macOS when the cluster is running |
| Windows Compose deployment is proven | `podman-compose` runs the full stack reliably on Windows/WSL2 |
| Must survive offline periods | A machine may be away for days; on next login it must catch up to the latest version |

---

## Options Considered

### Option A: Fix kind on Windows (unified ArgoCD on both platforms)

Run a full kind + ArgoCD stack on both machines, matching the macOS setup.

**Pros:** Consistent GitOps model across both machines; single CD mechanism to reason about.

**Cons:** kind with rootless Podman on WSL2 is unreliable — the API server returns HTML instead of JSON; kubeconfig is not written after cluster creation; this was attempted and abandoned. Fixing it would require either switching to Docker Desktop (licensed) or a different k8s distribution (k3d, k0s), both of which introduce new unknowns.

### Option B: Drop ArgoCD everywhere, Compose + polling on both (unified)

Use `podman-compose` on both machines with a background polling script that detects new GHCR image digests and redeploys.

**Pros:** Single mechanism across both platforms; simple; already proven on Windows.

**Cons:** Loses the GitOps model on macOS where ArgoCD already works; requires Compose to be stable on macOS (it runs there but hasn't been the primary deployment target).

### Option C: Hybrid — ArgoCD on macOS, Compose + polling on Windows *(chosen)*

Keep ArgoCD on the platform where it works; introduce Compose-based polling on the platform where it doesn't.

**Pros:** Both machines get zero-manual-step CD with mechanisms already proven on each platform. No time spent fixing kind on WSL2. macOS retains GitOps benefits.

**Cons:** Two different CD mechanisms to maintain; Windows deployments have up to 15 minutes of lag (polling interval) vs ArgoCD's ~3-minute poll. Divergence means a fresh Windows machine setup is different from macOS.

---

## Decision

**Option C: Hybrid** — ArgoCD on macOS, Compose + GHCR polling on Windows.

### Rationale

- ArgoCD on macOS is operational and produces automatic deployments when the kind cluster is running. Replacing it with Compose would be pure churn.
- kind + WSL2 rootless Podman failed in multiple attempts; investing more time in it is low-ROI for a personal machine.
- A 15-minute polling interval on Windows is acceptable — this is a personal newsreader, not a production SLA.
- Both paths use the same source of truth: `ghcr.io/deim0s13/newsbrief:latest` pushed by GitHub Actions CI.

---

## Implementation

### macOS — ArgoCD (GitOps)

```
CI pushes image → updates k8s/overlays/prod/kustomization.yaml
  ↓
ArgoCD polls git every 3 min → detects new image tag
  ↓
Sync wave 1: newsbrief-db-migrate Job (alembic upgrade head)
Sync wave 2: API Deployment rolls to new image
```

**Auto-start:** launchd runs `scripts/infra-start.sh` on every login. The script is idempotent — it creates the kind cluster if missing, waits for ArgoCD, and **applies `k8s/argocd/` Application CRs if they are not already registered**. This ensures ArgoCD survives cluster recreation after a reboot.

### Windows — Compose + GHCR polling

```
CI pushes image to ghcr.io/deim0s13/newsbrief:latest
  ↓
scripts/compose-watch.ps1 (daily at 06:00 via Task Scheduler)
  → podman pull :latest
  → compare running digest vs pulled digest
  → if newer: podman-compose up -d → wait for DB → alembic upgrade head
  → ntfy push notification on deploy
```

**Auto-start:** Task Scheduler fires `scripts/compose-start.ps1` at login (30s delay to let Podman Desktop initialise). Both scripts run silently (hidden PowerShell window) and require only Podman Desktop — no WSL2 at runtime.

**Install once:**
```powershell
powershell -ExecutionPolicy Bypass -File scripts\compose-task-install.ps1
```

### CI — unchanged

GitHub Actions already pushes:
- `ghcr.io/deim0s13/newsbrief:latest` on every merge to `main`
- `ghcr.io/deim0s13/newsbrief:v{version}` for tagged releases
- `ghcr.io/deim0s13/newsbrief:dev-latest` on every push to `dev`

Both CD paths track `:latest` (prod) or `:dev-latest` (dev environment).

---

## Consequences

### Positive
- Both machines deploy new versions without any manual commands after a PR merge
- Machines that have been offline automatically catch up on next login
- macOS retains full GitOps auditability (Git is the source of truth)
- Windows deployment is simple and robust (no k8s complexity)

### Negative
- Two different CD mechanisms to understand and maintain
- Windows has up to 15-minute deployment lag after CI completes
- A Windows-side failure (Podman offline, GHCR unreachable) silently skips the update and retries next poll cycle

### Neutral
- Both platforms use the same GHCR image, so the deployed artefact is identical
- Migrations run automatically on both paths (ArgoCD sync wave 1 on macOS; `alembic upgrade head` in watch script on Windows)

---

## Amendment — June 2026

The Windows CD scripts were converted from bash-via-WSL2 to native PowerShell (`scripts/compose-start.ps1`, `scripts/compose-watch.ps1`). The original bash scripts (`compose-start.sh`, `compose-watch.sh`) have been removed. WSL2 is now a developer tool only; the production runtime on Windows requires only Podman Desktop. The Task Scheduler installer (`scripts/compose-task-install.ps1`) was updated to invoke the PS1 scripts directly with `-WindowStyle Hidden` — no console window appears during gaming or fullscreen use.

## Related ADRs

- [ADR-0015: Local Kubernetes Distribution](0015-local-kubernetes-distribution.md)
- [ADR-0016: CI/CD Platform Migration](0016-cicd-platform-migration.md)
- [ADR-0017: GitOps Tooling](0017-gitops-tooling.md)
- [ADR-0019: CI/CD Pipeline Design](0019-cicd-pipeline-design.md)
