Use Cases (Runnable) + Test Cases
---------------------------------

Use Case 1: Code Duplication → Extract Method
- What: Move duplicate summation block in `process_data` to a new helper; replace with a call.
- Commands:
  ```powershell
  refactor-tool extract `
    --file examples\sample_project\sample\main.py `
    --function process_data `
    --start-line 10 --end-line 12 `
    --new-name compute_total `
    --return-var total `
    --preview
  refactor-tool extract `
    --file examples\sample_project\sample\main.py `
    --function process_data `
    --start-line 10 --end-line 12 `
    --new-name compute_total `
    --return-var total `
    --apply
  ```
- Test Case: Extract Duplicate Summation
  - Input: Run the two extract commands above on an unmodified sample.
  - Expected Output:
    - `compute_total(cleaned)` function added at module level, returning `total`.
    - Selected block replaced with call (`total = compute_total(cleaned)`).
    - `pytest -q tests` passes.

Use Case 2: Poorly Named Variables → Rename Variable
- What: Rename local loop variable `v` to `value` in `process_data`.
- Commands:
  ```powershell
  refactor-tool rename `
    --file examples\sample_project\sample\main.py `
    --function process_data `
    --name v --to value `
    --preview
  refactor-tool rename `
    --file examples\sample_project\sample\main.py `
    --function process_data `
    --name v --to value `
    --apply
  ```
- Test Case: Rename Local Variable in Scope
  - Input: Run the two rename commands above.
  - Expected Output:
    - All references to `v` within `process_data` are updated to `value` (no changes elsewhere).
    - `pytest -q tests` passes.

Use Case 3: Rename Function Across Files
- What: Project-wide rename of top-level function `dup_block` in `utils.py` to `extracted_helper`. Updates imports and call sites.
- Commands:
  ```powershell
  refactor-tool rename --file examples\sample_project\sample\utils.py `
    --name dup_block --to extracted_helper --preview
  refactor-tool rename --file examples\sample_project\sample\utils.py `
    --name dup_block --to extracted_helper --apply
  ```
- Test Case: Rename Top-level Function Project-wide
  - Input: Run the two rename commands above.
  - Expected Output:
    - Definition in `utils.py` renamed to `extracted_helper`.
    - Imports like `from .utils import dup_block` updated to `extracted_helper`.
    - Call sites updated accordingly (e.g., `combine` keeps working).
    - `pytest -q tests` passes.

Use Case 4: Long Function → Extract Function
- What: Split out average computation into `compute_avg` to shorten `process_data`.
- Commands:
  ```powershell
  refactor-tool extract `
    --file examples\sample_project\sample\main.py `
    --function process_data `
    --start-line 15 --end-line 15 `
    --new-name compute_avg `
    --return-var avg `
    --preview
  refactor-tool extract `
    --file examples\sample_project\sample\main.py `
    --function process_data `
    --start-line 15 --end-line 15 `
    --new-name compute_avg `
    --return-var avg `
    --apply
  ```
- Test Case: Extract Average Computation
  - Input: Run the two extract commands above (before or after Use Case 1; both work).
  - Expected Output:
    - `compute_avg(cleaned)` function added at module level, returning `avg`.
    - Original average computation replaced with a call assigning to `avg`.
    - `pytest -q tests` passes.