# Firebase / Cloud Run deployment status

## Status: backend target disabled

Elpis does **not** currently support a durable Firebase / Cloud Run backend
deployment. The application stores its state in SQLite and opens the database
in WAL mode. The former deployment mounted that database on Cloud Storage FUSE;
that storage contract is not safe for SQLite WAL or for Cloud Run revision
rollouts.

`scripts/firebase-deploy.sh` now fails before running any GCP, Docker, or Firebase
command. This is intentional. Do not bypass the guard with a manual Cloud Run
deploy.

The source-of-truth decision is recorded in
[ADR 0001: Keep SQLite on stable local disk](adr/0001-cloud-run-storage.md).

## Why this target is blocked

- SQLite WAL requires all database processes to share one host; SQLite documents
  that WAL does not work over a network filesystem.
- Cloud Storage FUSE is an object-storage filesystem, not a POSIX database disk.
- Cloud Run revisions can overlap during deployment. `--max-instances 1` does
  not fence an old revision from writing while a new revision starts.
- A local SQLite copy plus an object-storage heartbeat or ad-hoc restore process
  would not provide commit-level fencing and is not an accepted production
  design for this application.

References:

- [SQLite WAL limitations](https://sqlite.org/wal.html)
- [Cloud Run container filesystem](https://cloud.google.com/run/docs/container-contract#filesystem)
- [Cloud Storage FUSE considerations](https://cloud.google.com/storage/docs/gcsfuse-considerations)

## Supported deployment

Use the VPS deployment, which keeps SQLite on stable local disk:

```bash
./scripts/deploy.sh
```

See [VPS deployment](deploy-vps.md). Keep the service single-writer and back up
the database before migrations or updates.

## Re-enabling a managed cloud backend

Before restoring a Firebase / Cloud Run backend, the project needs all of the
following:

1. A transactional managed database adapter for `ContentStore` (for example,
   Cloud SQL PostgreSQL), including schema migrations and production credentials.
2. A deployment that has no SQLite database or SQLite WAL files on Cloud Storage
   FUSE.
3. An updated `firebase.json` `/api/**` rewrite pointing to the verified
   transactional backend.
4. Smoke tests covering restart, revision rollout, concurrent requests, and
   recovery after an interrupted deployment.
5. A documented backup and restore procedure tested against a real deployment.

Until those conditions are met, `firebase.json` intentionally contains only the
SPA fallback rewrite and no `/api/**` Cloud Run rewrite. A Firebase Hosting-only
deploy is therefore not a usable Elpis application: the frontend API client uses
same-origin `/api/...` requests and cookie authentication. The deployment guard
prevents that misleading path from being presented as successful.

`Dockerfile.cloudrun` is retained only as a future migration artifact; it is not
a supported production deployment target today.
