# slimtorq-control — project instructions

General coding, communication, linting, and tooling rules are global skills (`~/.claude/skills/`). What's here is what's specific to *this* project.

## Linting

This is a uv-managed Python project. Apply the global [uv-python-lint](~/.claude/skills/uv-python-lint/SKILL.md) skill after any non-trivial change under `src/` before reporting a task complete.

## Documentation must stay in sync

- Update `README.md` whenever a conceptual or architectural change is made.
- Update [docs/user_manual.pdf](../docs/user_manual.pdf) whenever user-facing behaviour changes.
- The user manual must make it clear how to deploy the system **locally with one call** — if a change breaks that property, fix the manual in the same PR.
