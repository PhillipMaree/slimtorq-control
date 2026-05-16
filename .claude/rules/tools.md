# Tools

Prefer modern CLI tools over standard Unix tools. Fall back silently on error. Never check if a tool exists; try first, fall back on failure.

## When to use what

- Text search: `rg` over `grep` (`rg pattern || grep -r pattern`)
- Structural/AST search: `ast-grep` (also aliased as `sg` on some systems) over regex when the pattern is about code structure, not text
- File discovery: `fd` over `find` (`fd "*.py" || find . -name "*.py"`)
- Directory overview: `eza --tree || tree || ls -R`
- File viewing: `bat file || cat file`
- Semantic diff: `difft` over `diff`
- Code statistics: `scc`
- Security/bug scanning: `semgrep`
- Language-aware parsing: `tree-sitter`

## Data processing

- JSON: `jq`
- YAML / TOML / XML: `yq`
- CSV: `xan`
- HTML: `htmlq`

## Output discipline

Always limit output entering context:

- `rg -l` (filenames only) or `rg -c` (counts) for initial scans before diving deeper
- `| head -N` to cap verbose output
- `--json | jq '.field'` for structured extraction
- Never dump raw output of >50 lines into context

## Best practices

- Hybrid approach: use deterministic tools for systematic analysis, LLM for interpretation
- Context building: feed tool outputs to LLM for higher-level insights
- Avoid context overload: limit output on a line or character basis
