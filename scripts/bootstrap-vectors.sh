#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck source=/dev/null
set -a
source .env
set +a
: "${QDRANT_API_KEY:?}"

# shellcheck source=scripts/data_paths.sh
source "$ROOT/scripts/data_paths.sh"
DATA_ROOT="$(data_root "$ROOT")"

python3 "$ROOT/scripts/render_vectors_config.py" \
  --data-root "$DATA_ROOT" \
  --api-key "$QDRANT_API_KEY"

COMPOSE_PROFILES=vectors podman compose up -d qdrant
echo "Qdrant ready on 127.0.0.1:${QDRANT_HTTP_PORT:-16333}"
