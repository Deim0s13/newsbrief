# CI/CD & GitOps Documentation

## Overview

NewsBrief's CI/CD pipeline runs entirely on **GitHub Actions** and delivers signed, scanned container images to GHCR. Deployment ("CD") is split by platform per [ADR-0032](../adr/0032-cross-platform-cd-strategy.md): **ArgoCD** (GitOps) on macOS, **Podman Compose + GHCR polling** on Windows.

> **History:** NewsBrief briefly ran CI on a local Tekton-in-kind stack (see [ADR-0016](../adr/0016-cicd-platform-migration.md)). That was replaced by the current GitHub Actions workflows — there is no Tekton, Smee webhook relay, or in-cluster registry in the live pipeline today. Ignore any lingering references elsewhere to `tkn`, `kind-registry:5000`, or webhook-triggered pipelines; they describe a retired setup.

## CI: GitHub Actions

Two workflows in `.github/workflows/`, both triggered by `push`:

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `ci-dev.yml` | push to `dev` | Lint, test, build & push `:dev-latest` + `:sha-{sha}`, update `k8s/overlays/dev/kustomization.yaml` |
| `ci-prod.yml` | push to `main` | Same + version-tag guard, Trivy scan, Cosign sign, SBOM, GitHub release, update `k8s/overlays/prod/kustomization.yaml` |

### `ci-dev.yml` jobs

```
lint ──┐
       ├──► build-and-push ──► update-manifest
test ──┘
```

1. **Lint** — `black --check`, `isort --check-only`
2. **Test** — `pytest` against a `pgvector/pgvector:pg16` service container, then `alembic upgrade head`; `mypy` runs but is non-blocking (`continue-on-error: true`)
3. **Build & Push** — multi-arch (`linux/amd64,linux/arm64`) build, pushes `ghcr.io/deim0s13/newsbrief:dev-latest` and `:sha-{short-sha}`
4. **Update k8s Manifest** — commits the new `sha-{short-sha}` tag into `k8s/overlays/dev/kustomization.yaml` with `[skip ci]`, so ArgoCD's dev Application picks it up

### `ci-prod.yml` jobs

```
check-version ──► lint ──┐
                 test ────┼──► build-and-push ──► security-scan ──► sign-image ──┐
                                                                  └► generate-sbom─┤
                                                                                    ├──► create-release ──► update-manifest
```

1. **Version check** — fails fast if `git tag` already contains `v{pyproject.toml version}`. **You must bump `[project].version` in `pyproject.toml` before merging to `main`, or this job blocks the whole pipeline.**
2. **Lint / Test** — same as `ci-dev.yml`
3. **Build & Push** — pushes `:v{version}`, `:latest`, and `:sha-{sha}`
4. **Security Scan** — Trivy: a non-blocking table scan for visibility, plus a SARIF scan that **fails the pipeline on CRITICAL CVEs with a known fix** (uploaded to GitHub Code Scanning)
5. **Sign Image** — Cosign key-based signing (`COSIGN_PRIVATE_KEY`/`COSIGN_PASSWORD` secrets), verified in the same job
6. **Generate SBOM** — Trivy CycloneDX SBOM, uploaded as a build artifact and attached to the release
7. **Create Release** — generates release notes from `git log {last_tag}..HEAD` and publishes a GitHub release tagged `v{version}` (checkout uses `fetch-depth: 0` — required for this history walk to see anything)
8. **Update k8s Manifest** — bumps `k8s/overlays/prod/kustomization.yaml` to `v{version}` with `[skip ci]`

### Versioning

There is **no automated semantic-release step** in either workflow — `[tool.semantic_release]` exists in `pyproject.toml` as future intent but isn't wired into CI. Versioning today is **manual**:

1. On `dev`, edit `version` in `pyproject.toml` and commit (`chore(release): bump version to X.Y.Z`)
2. `git checkout main && git merge dev --no-ff -m "chore(release): merge dev into main for vX.Y.Z"`
3. `git push origin main` — this triggers `ci-prod.yml`, which creates the tag, GitHub release, and signed image

See [BRANCHING_STRATEGY.md](BRANCHING_STRATEGY.md) for the full release flow (this repo uses a direct merge, not a PR, for `dev` → `main`).

## CD: Two platforms, two mechanisms (ADR-0032)

| | macOS | Windows |
|---|---|---|
| Mechanism | ArgoCD (GitOps) in a local `kind` cluster | `podman-compose` + GHCR digest polling |
| Watches | Git (`k8s/overlays/{dev,prod}/kustomization.yaml`) | `ghcr.io/deim0s13/newsbrief:latest` |
| Poll interval | 5 minutes (`timeout.reconciliation: 300s` in `k8s/argocd/argocd-cm.yaml`) | Daily at 06:00 (Task Scheduler → `compose-watch.ps1`) |
| Migrations | Argo CD sync-wave `Job` (`newsbrief-db-migrate`), runs before the API `Deployment` rolls | `alembic upgrade head` inside `compose-watch.ps1` before restart |
| Auto-start on boot | launchd → `scripts/infra-start.sh` (idempotent: creates cluster, waits for ArgoCD, re-applies `k8s/argocd/` Application CRs if missing) | Task Scheduler → `scripts/compose-start.ps1` |

Both platforms deploy from the **same GHCR image** — there's no separate build path per platform. See [KUBERNETES.md](KUBERNETES.md) for the macOS/ArgoCD side in detail, and `CLAUDE.md` → "Windows CD" for the Compose/PowerShell side.

### Database migrations

Schema changes live in `alembic/versions/` and are applied with `alembic upgrade head`.

| Context | How migrations run |
|---------|---------------------|
| **Local / Makefile** | `make migrate` or `make migrate-dev` (requires `DATABASE_URL`). See [DEVELOPMENT.md](DEVELOPMENT.md). |
| **CI (both workflows)** | The `test` job runs `alembic upgrade head` against the Postgres service container, so the revision chain is validated before merge. |
| **macOS / ArgoCD** | Sync-wave 1 `Job` (`newsbrief-db-migrate`) runs before the `Deployment` (wave 2) rolls. A failed migration blocks the rollout. |
| **Windows / Compose** | `compose-watch.ps1` runs `alembic upgrade head` after pulling a new image, before restarting the stack. |

**Authors:** create revisions with `make migrate-new MSG="short description"` and commit the new file alongside the code that needs the schema change.

## Container Registry

Images are published to GitHub Container Registry (GHCR):
- **Registry:** `ghcr.io`
- **Repository:** `ghcr.io/deim0s13/newsbrief`
- **Platforms:** `linux/amd64`, `linux/arm64`

| Tag | Produced by | Consumed by |
|-----|-------------|-------------|
| `dev-latest`, `sha-{sha}` | `ci-dev.yml` (push to `dev`) | ArgoCD dev Application (macOS) |
| `v{version}` | `ci-prod.yml` (push to `main`) | ArgoCD prod Application (macOS) |
| `latest` | `ci-prod.yml` (push to `main`) | Windows `compose-watch.ps1` |

## Security

| Feature | Tool | Where |
|---------|------|-------|
| Vulnerability scanning | Trivy | Both workflows can scan; `ci-prod.yml` also blocks on CRITICAL+fixable via SARIF |
| Image signing | Cosign (key-based, `COSIGN_PRIVATE_KEY`/`COSIGN_PASSWORD`) | `ci-prod.yml` only |
| SBOM generation | Trivy CycloneDX | `ci-prod.yml` only, attached to the GitHub release |
| Secrets | GitHub Actions secrets (`COSIGN_PRIVATE_KEY`, `COSIGN_PASSWORD`, `GITHUB_TOKEN`) | Repo Settings → Secrets |

There is no in-cluster secret manager (no Bitwarden/Vault integration) — Cosign keys live only as GitHub Actions secrets, used purely at build time.

## Notifications

Neither workflow posts to ntfy.sh anymore — the `Notify` job (a plain `curl` to
`ntfy.sh`) was removed (see ADR-0021's amendment) after repeatedly showing runs
as failed purely from a transient DNS/network hiccup reaching ntfy.sh, with no
timeout/retry/`continue-on-error` to absorb it — noise unrelated to whether the
pipeline itself actually passed. Use `gh run list`/`gh run view` (see
Troubleshooting below) for CI status instead.

ntfy.sh itself is still used for **infra-level** alerting outside CI — the
port-forward watchdog, `k8s-version-check.sh`, and Windows' `compose-watch.ps1`
— via the `NTFY_TOPIC` value in `.env` (a different value from the now-removed
GitHub Actions secret of the same name).

## Troubleshooting

```bash
# Check workflow status
gh run list --branch dev --limit 5
gh run list --branch main --limit 5

# View logs for a specific run (add --log-failed for just the failing steps)
gh run view <run-id>
gh run view <run-id> --log-failed

# Re-run a failed workflow
gh run rerun <run-id>
```

**`check-version` fails on push to `main`:** you forgot to bump `version` in `pyproject.toml` before merging — see [Versioning](#versioning) above.

**Empty "Changes in vX.Y.Z" section on a release:** the `create-release` job's checkout needs `fetch-depth: 0` to walk commit history; if this regresses, check that step still sets it.

**Cosign sign/verify fails:** confirm `COSIGN_PRIVATE_KEY`/`COSIGN_PASSWORD` secrets are current and `cosign.pub` in the repo root matches the key pair.

## Related Documentation

- [ADR-0016: CI/CD Platform Migration](../adr/0016-cicd-platform-migration.md) — history (Tekton → GitHub Actions)
- [ADR-0018: Secure Supply Chain](../adr/0018-secure-supply-chain.md) — Trivy, Cosign, SBOM rationale
- [ADR-0032: Cross-Platform CD Strategy](../adr/0032-cross-platform-cd-strategy.md) — why macOS and Windows use different CD mechanisms
- [KUBERNETES.md](KUBERNETES.md) — kind/ArgoCD setup detail (macOS)
- [BRANCHING_STRATEGY.md](BRANCHING_STRATEGY.md) — branch model and release process
