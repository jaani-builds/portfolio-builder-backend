#!/bin/bash
set -euo pipefail

docker rm -f portfolio-builder-backend >/dev/null 2>&1 || true
echo "portfolio-builder-backend stopped."
