#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Building portfolio-builder-backend image..."
docker build -t portfolio-builder-backend:local .

echo "Stopping existing backend container..."
docker rm -f portfolio-builder-backend >/dev/null 2>&1 || true

echo "Preparing backend data directory..."
mkdir -p "$SCRIPT_DIR/data"

ENV_FILE_ARGS=()
if [[ -f "$SCRIPT_DIR/.env" ]]; then
  ENV_FILE_ARGS=(--env-file "$SCRIPT_DIR/.env")
fi

echo "Starting backend on http://localhost:8000 ..."
docker run -d --name portfolio-builder-backend \
  "${ENV_FILE_ARGS[@]}" \
  -p 8000:8000 \
  -e APP_BASE_URL=http://localhost:8000 \
  -e FRONTEND_URL=http://localhost:5174 \
  -e PORTFOLIO_TEMPLATE_DIR=/app/portfolio_template \
  -v "$SCRIPT_DIR/data":/app/data \
  -v /Users/Jaani.Nickolas/Documents/projects/jaani-builds.github.io:/app/portfolio_template:ro \
  portfolio-builder-backend:local

echo ""
echo "Backend running at http://localhost:8000"
echo "API docs at http://localhost:8000/docs"
