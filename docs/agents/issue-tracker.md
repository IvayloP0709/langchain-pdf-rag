# Issue tracker: GitHub

Issues and PRDs for this repo live as GitHub issues. Use the `gh` CLI for all operations.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`. Use a heredoc for multi-line bodies.
- **Read an issue**: `gh issue view <number> --comments`, filtering comments by `jq` and also fetching labels.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` and `--state` filters.
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

Infer the repo from `git remote -v` — `gh` does this automatically when run inside a clone. This repo: `IvayloP0709/langchain-pdf-rag`.

## Pull requests as a triage surface

**PRs as a request surface: no.** This is a solo project — external PRs are not expected and are not run through `/triage`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`.

## Blocking dependencies

Tickets use GitHub's **native issue dependencies**, not a body-text convention. Set an edge with `gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>` (the blocker's numeric **database id** — `gh api repos/<owner>/<repo>/issues/<n> --jq .id`, not the `#number`). Read blockers back with `gh issue view <n> --json blockedBy` — a ticket is unblocked once every listed blocker is closed. This is what `scripts/ralph/ralph-prompt.md` checks before claiming a ticket.
