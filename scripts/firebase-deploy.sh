#!/usr/bin/env bash
#
# Firebase / Cloud Run deployment is intentionally disabled.
#
# Elpis currently stores all application state in a SQLite database opened in
# WAL mode. Cloud Storage FUSE is not a supported SQLite/WAL filesystem, and a
# Cloud Run revision rollout can overlap writers. A max-instances setting is
# not a writer lease. Do not re-enable this script until the backend uses a
# transactional managed database or an explicitly supported deployment design.

set -euo pipefail

case "${1:-}" in
  ""|--help|-h)
    cat <<'EOF'
Firebase / Cloud Run deployment is disabled for Elpis.

Reason: Elpis uses SQLite WAL, which must not be placed on Cloud Storage FUSE;
Cloud Run revision rollouts can overlap writers, and max-instances is not a
writer lease. Use ./scripts/deploy.sh for the stable local-disk VPS target, or
migrate ContentStore to a transactional managed database before re-enabling
this target.
EOF
    [[ "${1:-}" != "" ]] && exit 0
    ;;
  *)
    ;;
esac

printf '%s\n' \
  'ERROR: Firebase / Cloud Run deployment is disabled for Elpis.' \
  'Elpis uses SQLite WAL; Cloud Storage FUSE and overlapping Cloud Run' \
  'revisions are not a safe durable storage contract.' \
  'Use ./scripts/deploy.sh for a stable local-disk VPS deployment, or' \
  'migrate ContentStore to a transactional managed database first.' >&2
exit 1
