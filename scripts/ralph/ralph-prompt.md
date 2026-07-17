You implement and verify autonomously, then commit, push, and open a PR — a human reviews and merges it, you never merge or close the issue yourself (the issue closes automatically when the PR merges, via "Closes #<number>" in the PR body). Do exactly the following, once, then stop.

## 1. Find the next issue

List open issues on `IvayloP0709/langchain-pdf-rag` labeled `ready-for-agent`:

```
gh issue list --repo IvayloP0709/langchain-pdf-rag --state open --label ready-for-agent \
  --json number,title,assignees,body
```

For each candidate, in ascending issue-number order, check it qualifies:

- **Unassigned, or assigned only to you** — `assignees` is empty, or every login it contains matches your own (`gh api user --jq .login`). An issue assigned to a *different* login means another run claimed it — skip it. An issue assigned only to you is either unclaimed-in-practice or a prior attempt of yours that crashed before finishing — either way, take it; step 2 below covers resuming any work already in progress on it rather than starting over.
- **Unblocked** — `gh issue view <number> --repo IvayloP0709/langchain-pdf-rag --json blockedBy` returns no open blocking issues. If any listed blocker is still open, skip it.

Take the first qualifying issue in ascending number order.

If no issue qualifies, output exactly the line `<promise>COMPLETE</promise>` and stop — do not do anything else.

## 2. Create a branch (or resume one already in progress)

Name it after the issue, not a bare timestamp, so it's identifiable at a glance: `ralph/<number>-<slug>`, where `<slug>` is the issue title lowercased, non-alphanumeric runs replaced with `-`, trimmed of leading/trailing `-`, and cut to roughly 50 characters (the number alone guarantees uniqueness, so a truncated slug is fine — don't awkwardly abbreviate words to fit, just cut at a hyphen boundary).

Example: issue `#1 — Unify retrieval behind create_retriever + reranker config plumbing (no-op)` → `ralph/1-unify-retrieval-behind-create-retriever-reranker`.

Before creating anything, check whether a prior attempt already exists: run `git branch --show-current` and `git branch --list 'ralph/<number>-*'`.

- **No match** — create a fresh branch: `git checkout -b ralph/<number>-<slug>`.
- **Exactly one match (or you're already on it)** — a prior run on this issue didn't finish. Check it out instead of creating a new one (`git checkout -b` onto an existing branch name will fail). Then run `git status`; if there's already uncommitted or staged work, read what's already changed before writing anything new, and continue/finish it rather than starting over or discarding it.
- **More than one match** — the issue title likely changed between two prior attempts, producing two different slugs. Compare their last commits (`git log -1 --format='%H %ci %s' <branch>` for each) and resume the one with the most recent commit; note the other, stale branch(es) in your final summary so a human can clean them up.

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

## 7. Independent review before committing

Before staging anything, get a second, independent pass on your own work. The point is to catch what's invisible to you specifically because you just wrote it and have context and investment in your own approach — the same reason a human author shouldn't be the only reviewer of their own PR.

1. Capture the full diff for this issue: `git diff main...HEAD` (plus `git diff HEAD` if anything is still uncommitted).
2. Launch exactly one fresh agent via the Agent tool — a new agent, not a fork, so it shares none of your conversation context — with a prompt containing: the diff, the issue's acceptance criteria, and this instruction: "Review this diff for correctness bugs (wrong conditions, off-by-one, missing error handling, edge cases the tests don't cover) and for removed or weakened behavior (a guard, validation, or test case that existed before and is now gone or narrowed). Report each finding as file/line/summary/concrete failure scenario. If nothing is wrong, say so explicitly."
3. For each finding it returns: fix it, or decide it's a false positive / genuinely out of scope for this issue and say why in your final summary — don't silently drop a finding either way.
4. If you make any fix as a result, rerun the full feedback loop (step 6) before moving on — a fix is unverified until it's been tested.

This is a lighter, single-pass version of `/code-review`, proportionate to one autonomous run — not a substitute for the human review the PR still gets in step 8.

## 8. Commit, push, and open a PR

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

## 9. Stop

Do not start a second issue in this invocation, even if one is now unblocked — the branch/PR you just opened must be reviewable as a single, scoped unit. One issue's implementation per run. No merge and no issue-close without a human doing it; that only happens when a human merges the PR.
