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

# Branch creation happens inside ralph-prompt.md itself (step 2), once the
# issue is known, so the branch name can reflect it — not here, since at this
# point we don't yet know which issue (if any) will be picked.

for ((i = 1; i <= "$1"; i++)); do
  echo "=== Ralph iteration $i/$1 ==="

  # `tee /dev/stderr` prints each chunk to the terminal as it arrives, instead
  # of buffering the whole response until the command finishes — `result` still
  # gets the full text afterward (via the stdout side of the pipe) so the
  # <promise>COMPLETE</promise> check below still works.
  result=$(claude --permission-mode acceptEdits -p "$(cat "$prompt_file")" --verbose | tee /dev/stderr)

  if [[ "$result" == *"<promise>COMPLETE</promise>"* ]]; then
    echo "No more ready-for-agent issues after $i iteration(s)."
    exit 0
  fi
done

echo "Reached max iterations ($1) without exhausting the ready-for-agent backlog."
