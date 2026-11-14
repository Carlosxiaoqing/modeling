#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "$0")/.." && pwd)"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/salon-uv-cache}"
cd "$project_dir/backend"
runtime_args=()
if [[ -f "$project_dir/.runtime/provider.env" ]]; then
  runtime_args+=(--env-file "$project_dir/.runtime/provider.env")
fi
if [[ -f "$project_dir/.env" ]]; then
  runtime_args+=(--env-file "$project_dir/.env")
fi
exec uv run "${runtime_args[@]}" uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
