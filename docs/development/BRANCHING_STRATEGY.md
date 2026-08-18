# Git Branching Strategy

**Last Updated**: August 2026
**Status**: Active

---

This is a solo-maintained personal project. The branching model favors low ceremony over process: no required PR reviews, no branch protection rules — just two long-lived branches and a direct merge for releases. This document describes **what actually happens today**, not an aspirational process.

## 🌳 Branch Structure

### **`dev`** — Day-to-day development

- All feature work, fixes, and doc changes happen here — either as direct commits to `dev`, or via a short-lived `feature/*`/`fix/*` branch merged into `dev` for larger changes. Either is fine; there's no required PR.
- Every push runs `.github/workflows/ci-dev.yml`: lint → test → build & push `:dev-latest` + `:sha-{sha}` → update `k8s/overlays/dev/kustomization.yaml`.
- ArgoCD (macOS) auto-deploys the dev image to the `newsbrief-dev` namespace within ~5 minutes.

### **`main`** — Releases only

- Only receives a **direct merge from `dev`** when cutting a release — no PR, no required review, no branch protection rules enforced by GitHub.
- Pushing to `main` runs `.github/workflows/ci-prod.yml`: version-check gate → lint → test → build & push `:v{version}` + `:latest` → Trivy scan → Cosign sign → SBOM → GitHub release → update `k8s/overlays/prod/kustomization.yaml`.
- ArgoCD (macOS) auto-deploys within ~5 minutes; Windows picks up `:latest` the next morning at 06:00 via `compose-watch.ps1`.

### **`feature/*`, `fix/*`** (optional working branches)

Useful for isolating a larger change before merging into `dev`, but not required. Naming convention: `feature/issue-N-short-description`, `fix/issue-N-short-description`. Delete after merging.

---

## 📋 Release Process (what actually happens)

This is the sequence used for every release since v0.8.5, most recently v0.8.6:

1. **Finish and commit the work on `dev`**, verify `pytest`, `black`, `isort`, `mypy` are clean, and CI is green on `dev`.

2. **Bump the version** in `pyproject.toml` on `dev` and commit:
   ```bash
   # pyproject.toml: version = "X.Y.Z"
   git add pyproject.toml
   git commit -m "chore(release): bump version to X.Y.Z"
   git push origin dev
   ```
   `ci-prod.yml`'s `check-version` job fails the whole pipeline if this step is skipped — it checks that `vX.Y.Z` isn't already a tag.

3. **Merge `dev` into `main` directly** (no PR):
   ```bash
   git checkout main
   git pull origin main
   git merge dev --no-ff -m "chore(release): merge dev into main for vX.Y.Z"
   git push origin main
   ```

4. **CI takes it from there** — `ci-prod.yml` creates the `vX.Y.Z` tag, GitHub release (with auto-generated notes from `git log`), signed+scanned image, and SBOM. No manual tagging step.

5. **Update release docs** (this can happen before or after the merge — doesn't gate the pipeline):
   - Add an entry to `docs/releases/README.md`
   - Update the "Completed releases" table in `README.md`

6. **Sync local branches**:
   ```bash
   git checkout dev
   git merge main   # or: git pull, if dev and main have no divergent history
   ```

### Release Checklist

- [ ] Milestone issues closed on GitHub
- [ ] CI green on `dev`
- [ ] `pyproject.toml` version bumped and pushed to `dev` (before merging to `main`)
- [ ] `dev` merged into `main` with `--no-ff` (direct, no PR)
- [ ] `ci-prod.yml` completed successfully (check `gh run list --branch main --limit 3`)
- [ ] `docs/releases/README.md` and `README.md` updated

---

## 🏷️ Branch Naming (when using a working branch)

| Type | Example |
|------|---------|
| Feature | `feature/issue-262-rag-evaluation` |
| Fix | `fix/issue-99-clustering` |
| Docs | `docs/update-api-documentation` |
| Refactor | `refactor/story-generation-pipeline` |

## 📝 Commit Message Convention

[Conventional Commits](https://www.conventionalcommits.org/) style — used consistently but not enforced by a commit hook beyond `pre-commit`'s formatting/lint checks:

```
<type>(<scope>): <description>

[optional body]

[optional footer: Closes #N]
```

**Types in active use**: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`.

**Example** (real commit from the v0.8.6 cycle):
```
feat(rag): embedding reliability, semantic dedup, light RAG anchors, retrieval hook, and complexity scoring
```

Note: there is **no automated semantic-release** wired into CI — commit prefixes are a convention for readable history, not a version-bump trigger. Version bumps are the manual `pyproject.toml` edit in step 2 above.

---

## Why not required PRs / branch protection?

This was the original intent (see the git history of this file), but for a single-maintainer personal project the overhead of self-reviewing every PR added friction without a corresponding safety benefit — the real safety net is CI (lint + test + build) on every push to both branches, plus the version-check gate on `main`. If this project ever gains other contributors, branch protection + required reviews on `main` should be revisited.

## 📚 Additional Resources

- [CI/CD Guide](CI-CD.md) — full pipeline detail for `ci-dev.yml` / `ci-prod.yml`
- [Conventional Commits](https://www.conventionalcommits.org/)
