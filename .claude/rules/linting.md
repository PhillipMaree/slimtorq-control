# Linting

Python source under `src/` must pass the linters configured in [pyproject.toml](../../pyproject.toml) before a task is considered done. Run from the repo root:

```bash
uv run ruff check src/      # lint     (required — ruff is installed)
uv run ruff format src/     # format   (required — in-place)
uv run mypy src/            # types    (run if mypy is installed; configured under [tool.mypy])
uv run bandit -r src/       # security (run if bandit is installed; configured under [tool.bandit])
```

`ruff` is the only one currently in the dependency set. `mypy` and `bandit` are configured in `pyproject.toml` but not installed — `uv add --dev mypy bandit` if you want those passes to actually run.

## What `ruff check` enforces (from `[tool.ruff.lint]`)

| Code | Rule set |
|---|---|
| `E`, `W` | pycodestyle errors + warnings |
| `F` | pyflakes (unused imports / variables, undefined names) |
| `I` | isort (import ordering) |
| `N` | pep8-naming |
| `UP` | pyupgrade (modern Python idioms) |
| `B` | flake8-bugbear (likely bugs) |
| `C4` | flake8-comprehensions |
| `DTZ` | flake8-datetimez (require tz-aware datetimes) |
| `T10` | flake8-debugger (no `pdb` / `breakpoint` left in) |
| `EM` | flake8-errmsg (don't pass f-strings to exceptions) |
| `RUF` | Ruff-specific rules |

Line length: **180**. `sandbox/` is excluded.

## Rules
- Don't bypass with `# noqa` unless you can justify the specific rule waiver in a `# noqa: <CODE>  # <reason>` comment.
- Don't widen `disable_error_code` in `[tool.mypy]` to silence a real type error — fix the type instead.
- If a new module fails formatting on first save, run `ruff format` before continuing — don't re-edit until it's clean.
- After any non-trivial change to `src/`, run all three commands and resolve every diagnostic before reporting the task complete.
