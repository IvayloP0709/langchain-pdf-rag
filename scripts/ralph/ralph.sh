#!/usr/bin/env bash
# Ralph loop: repeatedly invoke Claude Code headlessly against ralph-prompt.md,
# each run picking up and closing one ready-for-agent GitHub issue, until the
# backlog is empty or --iterations is reached.
#
# Usage: scripts/ralph/ralph.sh <max-iterations> [--issue <number>]
#
# By default, each iteration auto-picks the lowest-numbered open, unblocked,
# unassigned `ready-for-agent` issue (ralph-prompt.md step 1). Pass `--issue
# <number>` to target one specific issue instead of auto-picking — in that
# case max-iterations is forced to 1, since a second iteration would just
# find the same issue already assigned (from iteration 1) and stop anyway.

set -euo pipefail

if [ -z "${1:-}" ]; then
  echo "Usage: $0 <max-iterations> [--issue <number>]"
  exit 1
fi

max_iterations="$1"
shift

issue_number=""
while [ $# -gt 0 ]; do
  case "$1" in
    --issue)
      issue_number="${2:-}"
      if [ -z "$issue_number" ]; then
        echo "Error: --issue requires a number" >&2
        exit 1
      fi
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [ -n "$issue_number" ] && [ "$max_iterations" != "1" ]; then
  echo "--issue $issue_number given: ignoring max-iterations=$max_iterations, running once."
  max_iterations=1
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
prompt_file="$script_dir/ralph-prompt.md"

prompt_text="$(cat "$prompt_file")"
if [ -n "$issue_number" ]; then
  # Prepended ahead of ralph-prompt.md's own step 1 so it takes precedence:
  # skip auto-picking and go straight to the given issue. The qualification
  # rules (self-vs-other assignee) and branch-resume handling now live in
  # ralph-prompt.md steps 1-2 themselves — shared with the auto-pick path —
  # so this override just points at the one issue and defers to those rules
  # instead of re-stating them here.
  override="OVERRIDE for step 1 (\"Find the next issue\") below: work on issue #$issue_number specifically — do not run the \`gh issue list\` auto-pick query. Still verify it qualifies against the same rules as step 1 above: run \`gh issue view $issue_number --repo IvayloP0709/langchain-pdf-rag --json state,assignees,blockedBy\`. If it is not open, or has an open blocker, or is assigned to a login other than your own (check via \`gh api user --jq .login\`), stop immediately and report exactly why — do not pick a different issue or proceed anyway. Otherwise continue with step 2 onward, using issue #$issue_number — step 2 already covers resuming a branch/work-in-progress left by a prior attempt on this same issue."
  prompt_text="$override

$prompt_text"
fi

# Branch creation happens inside ralph-prompt.md itself (step 2), once the
# issue is known, so the branch name can reflect it — not here, since at this
# point we don't yet know which issue (if any) will be picked.

for ((i = 1; i <= max_iterations; i++)); do
  echo "=== Ralph iteration $i/$max_iterations ==="

  # Plain `-p` text output buffers internally until the whole turn finishes —
  # `tee` alone doesn't fix that, since there's nothing incremental to tee.
  # `--output-format stream-json` makes Claude emit one JSON event per line as
  # it happens; ralph_format_stream.py turns those into live colored diffs for
  # Edit/Write/MultiEdit tool calls (plus a line per Bash command run), and
  # `tee /dev/stderr` streams that formatted text to the terminal as it's
  # produced while `result` still gets the full text afterward, so the
  # <promise>COMPLETE</promise> check below still works.
  result=$(claude --permission-mode acceptEdits -p "$prompt_text" --verbose --output-format stream-json \
    | python3 -u "$script_dir/ralph_format_stream.py" \
    | tee /dev/stderr)

  if [[ "$result" == *"<promise>COMPLETE</promise>"* ]]; then
    echo "No more ready-for-agent issues after $i iteration(s)."
    exit 0
  fi
done

echo "Reached max iterations ($max_iterations) without exhausting the ready-for-agent backlog."
