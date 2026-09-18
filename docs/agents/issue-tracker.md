# Issue tracker: GitHub

Issues and specifications for this repository live in [GitHub Issues for `Lilb1tty/HermesMux`](https://github.com/Lilb1tty/HermesMux/issues). Use the GitHub CLI for issue operations, explicitly targeting `Lilb1tty/HermesMux` when the current directory is not a clone.

## Conventions

- **Create an issue**: `gh issue create --repo Lilb1tty/HermesMux --title "..." --body "..."`
- **Read an issue**: `gh issue view <number> --repo Lilb1tty/HermesMux --comments`, including its labels.
- **List issues**: `gh issue list --repo Lilb1tty/HermesMux --state open --json number,title,body,labels,comments`, with suitable `--label` filters.
- **Comment on an issue**: `gh issue comment <number> --repo Lilb1tty/HermesMux --body "..."`
- **Apply or remove labels**: `gh issue edit <number> --repo Lilb1tty/HermesMux --add-label "..."` or `--remove-label "..."`.
- **Close an issue**: `gh issue close <number> --repo Lilb1tty/HermesMux --comment "..."`

## Pull requests as a triage surface

**PRs as a request surface: no.** Set this to `yes` only if external pull requests should enter the same triage queue as issues.

## When a skill says "publish to the issue tracker"

Create a GitHub issue in `Lilb1tty/HermesMux`.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --repo Lilb1tty/HermesMux --comments`.

## Wayfinding operations

For `/wayfinder`, the **map** is one issue labeled `wayfinder:map`, with child issues as tickets.

- Create a map with `gh issue create --repo Lilb1tty/HermesMux --label wayfinder:map`.
- Create children as GitHub sub-issues when available; otherwise, link them in the map task list and add `Part of #<map>` to each child.
- Represent blockers with GitHub native issue dependencies when available; otherwise, add `Blocked by: #<n>` to the child issue.
- Claim a ticket with `gh issue edit <n> --repo Lilb1tty/HermesMux --add-assignee @me`.
- Resolve a ticket by commenting, closing it, and adding any useful context pointer to the map.
