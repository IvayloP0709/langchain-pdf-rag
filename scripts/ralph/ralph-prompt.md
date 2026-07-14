You implement and verify autonomously, then commit, push, and open a PR — a human reviews and merges it, you never merge or close the issue yourself (the issue closes automatically when the PR merges, via "Closes #<number>" in the PR body). Do exactly the following, once, then stop.

## 1. Find the next issue

List open issues on `IvayloP0709/langchain-pdf-rag` labeled `ready-for-agent`:

```
gh issue list --repo IvayloP0709/langchain-pdf-rag --state open --label ready-for-agent \
  --json number,title,assignees,body
```

For each candidate, in ascending issue-number order, check it qualifies:

- **Unassigned** — `assignees` is empty. If it already has an assignee, skip it (another run claimed it).
- **Unblocked** — `gh issue view <number> --repo IvayloP0709/langchain-pdf-rag --json blockedBy` returns no open blocking issues. If any listed blocker is still open, skip it.

Take the first qualifying issue in ascending number order.

If no issue qualifies, output exactly the line `<promise>COMPLETE</promise>` and stop — do not do anything else.

## 2. Create a branch

Name it after the issue, not a bare timestamp, so it's identifiable at a glance: `ralph/<number>-<slug>`, where `<slug>` is the issue title lowercased, non-alphanumeric runs replaced with `-`, trimmed of leading/trailing `-`, and cut to roughly 50 characters (the number alone guarantees uniqueness, so a truncated slug is fine — don't awkwardly abbreviate words to fit, just cut at a hyphen boundary).

Example: issue `#1 — Unify retrieval behind create_retriever + reranker config plumbing (no-op)` → `ralph/1-unify-retrieval-behind-create-retriever-reranker`.

```
git checkout -b ralph/<number>-<slug>
```

## 3. Claim it

Immediately, before any other work:

```
gh issue edit <number> --repo IvayloP0709/langchain-pdf-rag --add-assignee @me
```

This must happen first so a concurrent run doesn't pick the same issue.

## 4. Read before writing

Fetch the issue's full body and comments:

```
gh issue view <number> --repo IvayloP0709/langchain-pdf-rag --comments
```

If it references a spec under `docs/specs/`, read that in full too — the issue is a slice of it, not a replacement for it. Before touching any code:

- Read every file the issue's "Implementation Decisions" section names, as it exists today, not as you remember similar code working elsewhere.
- Read `docs/agents/domain.md` and any ADRs it points at for this area.
- List out, in your own working notes, each line of the issue's "Acceptance criteria" checklist as a separate item you will individually verify later — don't treat the checklist as a vague summary of the goal.

## 5. Implement against each acceptance criterion, test-first

Work through the "Acceptance criteria" checklist one item at a time, not as a single undifferentiated pass over the codebase:

1. For a criterion that specifies behavior (not pure plumbing/config), write the test for it first, using the seam and prior art named in the issue's "Testing Decisions" section. Confirm it fails before writing the implementation — a test that passes before the implementation exists is testing nothing.
2. Write the minimum implementation change to make that test pass.
3. Move to the next criterion. Don't batch multiple criteria into one untested change.

Keep the diff scoped to this one issue. If you notice an unrelated improvement or bug while working, do not fix it inline — note it in your final summary instead.

## 6. Feedback loop: run it, don't assume it

After each criterion, and again at the end, run:

- The full test suite (not just the new tests — confirm nothing existing broke).
- Lint/format checks (`ruff`, `black --check`) and typechecking if the project has a configured typechecker.

If anything fails, do not move on and do not report success — read the actual failure output, fix the specific cause, and rerun. Repeat this diagnose-fix-rerun cycle until the run is clean. If the same failure persists after 3 fix attempts, stop implementing further criteria, leave the failing state as-is, and report the exact failure and what you tried in your final summary rather than silently working around it (e.g. by deleting or weakening a test).

## 7. Commit, push, and open a PR

Do **not** merge the PR and do **not** close the issue directly — a human reviews and merges it; the issue closes automatically on merge via the "Closes #<number>" line below.

1. Stage with `git add <files>`, then commit with a message focused on *why*, ending with the trailer `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`. **Do not use a heredoc / `$(cat <<EOF ... EOF)` for the message** — this sandbox denies any command containing `$(...)` command substitution outright, with no allowlist override possible, so it will silently fail every time. Instead pass each paragraph as its own `-m` flag, which is git's native way to build a multi-paragraph message without a subshell:
   ```
   git commit -m "<title>" -m "<body paragraph>" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
   ```
2. Push the branch: `git push -u origin ralph/<number>-<slug>`
3. Open the PR, using the structured summary below as the body with `Closes #<number>` appended. **Same rule as above — no heredoc/`$(...)` here either.** Pass `--body` as one literal double-quoted string with real newline characters embedded directly in it (still a single simple command, no subshell):
   ```
   gh pr create --repo IvayloP0709/langchain-pdf-rag \
     --title "<concise, imperative title>" \
     --body "<structured summary, see template below, with literal newlines>

   Closes #<number>"
   ```

Use this template for both the PR body and stdout, filled in concretely — not a restatement of the issue body:

```
## Issue

#<number> — <title>

## Changes

- <file/module>: <what changed and why, one line>
- <file/module>: <what changed and why, one line>
  (one line per file touched — name the actual behavior, not "updated X")

## Tests

- <N> tests added/changed: <what each one asserts, briefly>
- Full suite: <pass count>/<total> passing, <fail count> failing
- Lint/typecheck: <clean, or what's still failing and why>

## Acceptance criteria

- [x] <criterion, verbatim from the issue> — <how you verified it>
- [ ] <criterion> — <why it's not done: blocked, uncertain, deferred>

## Unblocks

<any other open issue whose blockers this closes out, per its "blocked-by" list>

## Notes for the reviewer

<anything you're unsure about, anything out-of-scope you noticed but didn't fix, any assumption you made that the issue didn't specify>
```

## 8. Stop

Do not start a second issue in this invocation, even if one is now unblocked — the branch/PR you just opened must be reviewable as a single, scoped unit. One issue's implementation per run. No merge and no issue-close without a human doing it; that only happens when a human merges the PR.
