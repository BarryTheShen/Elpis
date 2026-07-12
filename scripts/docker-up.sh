#!/usr/bin/env bash
# Start web UI only (digest + admin + ratings). No Ollama in Docker.
# CONDENSEIT_DOCKER_UI_BEST_EFFORT=1: ignore compose failures (used by docker-run.sh).
set -euo pipefail
source "$(dirname "$0")/lib/common.sh"
ensure_config
mkdir -p data/digests
log "Starting Elpis web UI on :8899"

compose_up() {
  docker compose up -d --build
}

if [[ "${CONDENSEIT_DOCKER_UI_BEST_EFFORT:-}" == "1" ]]; then
  compose_up 2>/dev/null || true
else
  compose_up
fi
log "Digest: http://localhost:8899/"
log "Admin:  http://localhost:8899/admin/"
log "Run pipeline on host: ./scripts/native-run.sh"
