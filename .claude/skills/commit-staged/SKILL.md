---
name: commit-staged
description: Commit staged changes
disable-model-invocation: true
allowed-tools: Bash(git status *) Bash(git log *) Bash(git diff *) Bash(git show *)
---

Commit the currently staged changes as a single commit.

Here are the staged changes:
```!
git diff --cached
```

Follow the commit message conventions of this repository:
!`git log --oneline -10`

Rules:

- Prefix with the Jira ticket ID (e.g. `EDGE-123 Add foo`). If the ticket ID is unclear from context or recent history, ask the user before committing.
- Use imperative mood: "Add", "Fix", "Update" (not "Added", "Fixes").
- Keep the subject line (including prefix) to 80 characters or fewer.
- Add a blank line after the subject, followed by a short body (2-4 lines max) focused on *why* — the rationale, motivation, or tradeoff. Avoid restating what the diff already shows.
- Do NOT commit unstaged or untracked files.
