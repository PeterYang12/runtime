#!/usr/bin/env bash
# Run bench.py against the local E2B compose stack.
#   ./run.sh env
#   ./run.sh create --template swesmith-090a7c94c767-m2
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
COMPOSE="$HERE/../embed/compose"
eval "$(cd "$COMPOSE" && docker compose exec -T ready cat /run/e2b/sdk.env)"
# Talk to the api and client-proxy directly on this host (no nginx, no WAN).
export E2B_API_URL=http://127.0.0.1:3000 E2B_SANDBOX_URL=http://127.0.0.1:3002
exec "$HERE/.venv/bin/python" -I "$HERE/bench.py" "$@"
