#!/usr/bin/env bash
# Ralph loop: repeatedly invoke Claude Code headlessly against ralph-prompt.md,
# each run picking up and closing one ready-for-agent GitHub issue, until the
# backlog is empty or --iterations is reached.
#
# Usage: scripts/ralph.sh <max-iterations>

set -euo pipefail

if [ -z "${1:-}" ]; then
  echo "Usage: $0 <max-iterations>"
  exit 1
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
prompt_file="$script_dir/ralph-prompt.md"

branch="ralph/$(date +%Y%m%d-%H%M%S)"
git checkout -b "$branch"
echo "Working on branch: $branch"

for ((i = 1; i <= "$1"; i++)); do
  echo "=== Ralph iteration $i/$1 ==="

  result=$(claude --permission-mode acceptEdits -p "$(cat "$prompt_file")")
  echo "$result"

  if [[ "$result" == *"<promise>COMPLETE</promise>"* ]]; then
    echo "No more ready-for-agent issues after $i iteration(s)."
    exit 0
  fi
done

echo "Reached max iterations ($1) without exhausting the ready-for-agent backlog."
