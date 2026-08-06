# Firebase / Cloud Run deployment status

This target is intentionally disabled. Do not run or improvise a Firebase /
Cloud Run deployment for Elpis.

Elpis stores application state in SQLite WAL. Cloud Storage FUSE is not a safe
SQLite/WAL filesystem, and Cloud Run revision rollouts can overlap writers.
`--max-instances 1` is not a writer lease. A local SQLite copy plus an ad-hoc
object-storage heartbeat or restore process is not an accepted production fix.

The repository guard is `scripts/firebase-deploy.sh`; it exits before invoking
`gcloud`, Docker, or Firebase. `firebase.json` contains only the SPA fallback
rewrite and no `/api/**` Cloud Run rewrite. A Hosting-only deployment is not a
usable Elpis application because the frontend uses same-origin `/api/...`
requests and cookie authentication.

## Supported deployment

Use the stable local-disk VPS target instead:

```bash
./scripts/deploy.sh
```

Follow [VPS deployment](../deploy-vps.md). Keep one SQLite writer on stable
local disk and back up the database before migrations or updates.

## Requirements before re-enabling Cloud Run

A future Cloud Run deployment must first provide:

1. A transactional managed database adapter for `ContentStore` (for example,
   Cloud SQL PostgreSQL) and migrations.
2. No SQLite database or WAL files on Cloud Storage FUSE.
3. A verified `/api/**` Firebase rewrite to that transactional backend.
4. Restart, revision-rollout, concurrent-write, and interrupted-deployment
   recovery smoke tests against the real target.
5. A tested backup and restore procedure.

References:

- [SQLite WAL](https://sqlite.org/wal.html)
- [Cloud Run filesystem contract](https://cloud.google.com/run/docs/container-contract#filesystem)
- [Cloud Storage FUSE considerations](https://cloud.google.com/storage/docs/gcsfuse-considerations)
