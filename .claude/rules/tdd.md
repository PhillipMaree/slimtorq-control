# Test-Driven Development

Follow TDD when implementing logic:

1. **Red** — Write a failing test that defines the expected behaviour. Do not write production code without a failing test.
2. **Green** — Write the minimum code to make the test pass.
3. **Refactor** — Clean up while keeping tests green.

## Rules

- One test at a time. Do not batch multiple behaviours into one cycle.
- Run tests after each step to confirm red → green → green.
- Tests define the interface — let test code drive API design decisions.
- Name tests to describe behaviour, not implementation (`"returns total for valid items"`, not `"test calculateTotal"`).
- When fixing a bug, first write a test that reproduces it, then write the fix.
- Do not skip the red step — a test that never failed proves nothing.
