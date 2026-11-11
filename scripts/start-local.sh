#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
docker compose up -d --build
printf '\n화면: http://localhost:5173\nAPI: http://localhost:8000/api/health\n상태: docker compose ps\n중지: docker compose down\n'
