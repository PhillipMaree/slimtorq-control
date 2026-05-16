---
name: commit-all
description: Commit all changes as logical commits
disable-model-invocation: true
allowed-tools: Bash(git status *) Bash(git log *) Bash(git diff *) Bash(git show *)
---

Review all staged, unstaged, and untracked changes in the working tree.

```!
git status --short
```

Group them into one or more logical commits. Each commit should represent a single coherent change (e.g. a refactor, a bug fix, a new feature, a config change). Stage and commit them in a logical order — foundational changes first, dependent changes after.

Follow the commit message conventions of this repository:
!`git log --oneline -10`

Rules:

- Prefix with the Jira ticket ID (e.g. `EDGE-123 Add foo`). If the ticket ID is unclear from context or recent history, ask the user before committing.
- Use imperative mood: "Add", "Fix", "Update" (not "Added", "Fixes").
- Keep the subject line (including prefix) to 80 characters or fewer.
- Add a blank line after the subject, followed by a short body (2-4 lines max) focused on *why* — the rationale, motivation, or tradeoff. Avoid restating what the diff already shows.
- Present the planned commits (files and message) to the user for approval before executing.
