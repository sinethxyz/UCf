# SKILL.md — review-diff

## Description
Reviews a code diff and produces a structured verdict.

## When to Use
- A Foundry run reaches the reviewing phase.
- A PR is opened and needs automated review.
- Explicitly invoked via `/review-diff`.

## Workflow

1. **Read the full diff.** `git diff base_branch...HEAD` in the worktree.

2. **For each changed file:**
   a. Read the full file (not just the diff hunk) for context.
   b. Check: does the change match existing patterns in the module?
   c. Check: are error cases handled?
   d. Check: are there security implications?

3. **Check contracts.**
   - If API routes changed: does the OpenAPI spec match?
   - If domain models changed: does the JSON Schema match?
   - If new endpoints: are they registered in routes?

4. **Check test coverage.**
   - Are new functions tested?
   - Are error paths tested?
   - Do existing tests still make sense with the changes?

5. **Produce ReviewVerdict.** Structured JSON with verdict, issues, and summary.

## Output
ReviewVerdict JSON validated against `foundry/contracts/review_models.py::ReviewVerdict`.
