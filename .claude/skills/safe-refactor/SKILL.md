# SKILL.md — safe-refactor

## Description
Performs structural code changes in atomic, verifiable steps. Each step is independently tested.

## When to Use
- Task type is `refactor`.
- Plan involves renaming, extracting, moving, or reorganizing code without changing behavior.
- Explicitly invoked via `/safe-refactor`.

## Workflow

1. **Inventory usages.** Before any change, `Grep` for all references to the target symbol, module, or pattern.

2. **Plan atomic steps.** Break the refactor into the smallest possible independent steps. Each step must leave the codebase in a compilable, test-passing state.

3. **Execute step by step.** For each step:
   a. Make the change.
   b. Run `go build ./...` (or `tsc --noEmit`).
   c. Run `go test ./...` (or `npm test`).
   d. If tests fail, **revert the step** and report the failure.

4. **Verify all usages updated.** After all steps, re-run the usage inventory. If any references remain, they are bugs.

5. **Final verification.** Full build + full test suite.

## Constraints
- Never combine behavioral changes with structural changes.
- If a refactor requires a behavioral change to work, stop and report — the plan needs revision.
- Maximum 3 retry attempts per step before marking the step as failed.

## Output
Clean diff with all steps applied. Verification results.
