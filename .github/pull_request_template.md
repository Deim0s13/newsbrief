## Summary

<!-- Briefly describe the change. -->

## Checklist

- [ ] Tests and **pre-commit** pass where relevant.
- [ ] **Database migrations:** either **not applicable** (no `alembic/versions/` changes), **or** the rollout path for **each** environment will run **`alembic upgrade head`** before (or as part of) serving the new code:
  - **Kubernetes / Argo CD:** `newsbrief-db-migrate` Job (sync wave) — see [KUBERNETES.md](docs/development/KUBERNETES.md#sync-waves).
  - **Local / VM / manual:** `make migrate` or `make migrate-dev` with correct `DATABASE_URL` — see [CONTRIBUTING.md](CONTRIBUTING.md#database).
