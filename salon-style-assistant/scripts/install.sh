#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "$0")/.." && pwd)"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/salon-uv-cache}"
cd "$project_dir/backend"
uv sync --frozen
if [[ -f "$project_dir/.env" ]]; then
  uv run --env-file "$project_dir/.env" alembic upgrade head
else
  uv run alembic upgrade head
fi
cd "$project_dir/apps/web"
npm ci --cache /tmp/salon-npm-cache
npm run build
