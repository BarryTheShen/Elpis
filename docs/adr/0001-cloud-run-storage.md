# ADR 0001: Keep SQLite on stable local disk

- **Status:** Accepted
- **Date:** 2026-07-13

## Context

Elpis uses SQLite with WAL enabled and has background scheduler and web-request
writers. The former Firebase / Cloud Run deployment mounted the SQLite data
directory on Cloud Storage FUSE and relied on `--max-instances 1` for writer
coordination. Cloud Run revisions can overlap during rollout, and a max-instance
setting is not a fencing token. SQLite WAL requires participating processes to
share a host and is not supported over a network filesystem.

## Decision

The supported production deployment is the VPS target, where the single SQLite
writer uses stable local disk (`scripts/deploy.sh`). The Firebase / Cloud Run
backend deployment is disabled. `scripts/firebase-deploy.sh` fails before any
cloud-side mutation, and `firebase.json` has no `/api/**` Cloud Run rewrite.

## Rejected alternatives

- **SQLite on Cloud Storage FUSE:** rejected because object-storage filesystem
  semantics do not provide the SQLite WAL and fsync contract required for a
  durable database.
- **Litestream plus a GCS heartbeat lease:** rejected as a drop-in solution.
  Revision overlap, lease expiry, and paused processes require fencing enforced
  on every commit; SQLite cannot enforce a GCS lease token against writes.
- **Cloud Run with `--max-instances 1`:** rejected as coordination. It does not
  guarantee one writer across revisions during deployment.

## Consequences

- Firebase / Cloud Run is not an available backend deployment target today.
- VPS deployment remains the documented production path and must retain one
  SQLite writer on local disk with tested backups.
- The existing Cloud Run Dockerfile is retained only as a migration artifact.
- Firebase Hosting alone is not a usable Elpis deployment because the SPA uses
  same-origin `/api/...` requests and cookie authentication.

## Re-enable criteria

Re-enable a managed cloud backend only after all of these are complete:

1. `ContentStore` is backed by a transactional managed database, such as Cloud
   SQL PostgreSQL, with migrations and tested credentials.
2. No SQLite database, WAL, or ad-hoc replication files are used on Cloud
   Storage FUSE.
3. The `/api/**` Firebase rewrite targets the verified transactional backend.
4. Restart, revision-rollout, concurrent-write, interrupted-deployment, and
   backup/restore smoke tests pass against the real deployment.
5. The deployment and rollback runbooks are updated and reviewed.
