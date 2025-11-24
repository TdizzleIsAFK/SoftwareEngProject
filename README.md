Refactoring Tool (Prototype)

A prototype Python refactoring tool that can:

- Analyze an existing codebase
- Safely rename symbols (variables, functions, classes) across files
- Extract a contiguous block of code into a new function
- Improve readability via formatting and hygiene transforms

This prototype targets the needs described in the Functional Needs Statement and includes a small example project and spec runner.

Installation

```bash
# From the repository root
python -m venv .venv
. .venv/Scripts/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e .
```

Or install dependencies for development:

```bash
pip install -r requirements.txt
```

CLI Usage

```bash
refactor-tool --help
```

Analyze

```bash
refactor-tool analyze . --include "**/*.py" --exclude "**/.venv/**,**/__pycache__/**"
```

Rename

Top-level function/class across project (requires the defining file to infer module path):

```bash
refactor-tool rename --file path/to/module.py --name old_func --to new_func --preview
refactor-tool rename --file path/to/module.py --name old_func --to new_func --apply
```

Local variable inside a single function:

```bash
refactor-tool rename --file path/to/module.py --function target_func --name x1 --to student_name --preview
```

Extract Function

```bash
refactor-tool extract --file path/to/module.py --function target_func \
  --start-line 42 --end-line 58 --new-name helper_func --preview

# Apply the change
refactor-tool extract --file path/to/module.py --function target_func \
  --start-line 42 --end-line 58 --new-name helper_func --apply
```

Readability (tidy)

```bash
# Normalize newlines, strip hidden chars, remove dead imports (safe), keep indentation default (4 spaces)
refactor-tool tidy . --strip-hidden --remove-dead-imports --preview
refactor-tool tidy . --strip-hidden --remove-dead-imports --apply
```

Include/Exclude and Preview

All commands that change files accept:

- `--include` and `--exclude` glob patterns (comma-separated)
- `--preview` to show diffs without writing
- `--apply` to write changes

Example Project and Spec Runner

A small example lives under `examples/sample_project`. Run its tests before and after refactors to confirm no behavior change:

```bash
pytest -q examples/sample_project/tests
```

You can also run the built-in spec runner:

```bash
refactor-tool spec examples/sample_project
```

This runner performs a rename and an extract on the sample project, then runs tests to validate.

Notes and Limitations (Prototype)

- Rename across files leverages static analysis via LibCST. Ambiguous or unsafe cases are refused with explanations.
- Extract supports ranges that align with complete statements and simple return propagation; complex control flow is refused.
- Dead import removal is conservative; wildcard imports and dynamic usage are preserved.

License

MIT


