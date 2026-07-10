You implement and verify autonomously, but a human reviews your work before it becomes permanent — do not commit and do not close the issue. Do exactly the following, once, then stop.

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

## 2. Claim it

Immediately, before any other work:

```
gh issue edit <number> --repo IvayloP0709/langchain-pdf-rag --add-assignee @me
```

This must happen first so a concurrent run doesn't pick the same issue.

## 3. Implement it

Read the issue's full body (`gh issue view <number> --repo IvayloP0709/langchain-pdf-rag --comments`) and, if it references one, the linked spec under `docs/specs/`. Follow this repo's `/implement` skill process:

- Explore the relevant code before changing it.
- Use TDD at the seams the issue's "Testing Decisions" describe, where applicable.
- Satisfy every item in the issue's "Acceptance criteria" checklist.

## 4. Verify

Run the full test suite and typechecking. Do not proceed to commit if anything fails — fix it first. Only a single issue's worth of work should be in the diff.

## 5. Stop for review

Do **not** commit and do **not** close the issue — leave the changes uncommitted on the current branch so a human can review the diff first.

Print a short summary before stopping:

- Which issue (`#<number>`, title) this was.
- Files changed and what changed in each, briefly.
- Test suite / typecheck results.
- Any acceptance criteria you were unsure about or couldn't fully verify.

## 6. Stop

Do not start a second issue in this invocation, even if one is now unblocked. One issue's implementation per run — and no commit or issue-close without a human doing it.
