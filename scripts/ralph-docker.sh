#!/usr/bin/env bash
# One-line wrapper around the full `docker run` invocation for the Ralph loop.
# Builds the image if it doesn't exist yet, then runs scripts/ralph.sh inside
# the container for <max-iterations>.
#
# Usage: scripts/ralph-docker.sh <max-iterations>

set -euo pipefail

if [ -z "${1:-}" ]; then
  echo "Usage: $0 <max-iterations>"
  exit 1
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"

docker build -f "$script_dir/ralph.Dockerfile" -t ralph-sandbox "$repo_root"

docker run --rm \
  --env-file "$repo_root/.env" \
  -v "$repo_root":/workspace \
  -v "$script_dir/ralph-claude-config.json":/root/.claude.json \
  -w /workspace \
  ralph-sandbox \
  "$1"
