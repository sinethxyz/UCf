# PR Standards

## Branch Naming
All Foundry-generated branches follow: `foundry/{task-type}-{short-kebab-description}`

Examples:
- `foundry/endpoint-build-company-timeline`
- `foundry/bug-fix-search-pagination`
- `foundry/refactor-event-normalization`
- `foundry/extraction-batch-funding-signals`

## PR Title
Format: `[Foundry] {task type}: {short description}`

Examples:
- `[Foundry] endpoint_build: Add GET /v1/companies/{id}/timeline`
- `[Foundry] bug_fix: Fix off-by-one in search pagination`
- `[Foundry] refactor: Extract event normalization into shared module`

## PR Body

Every Foundry-generated PR body must contain:

```markdown
## Summary
{1-2 sentence description of what changed and why}

## Plan
{Link to plan artifact or inline summary of planned steps}

## Changes
{File-by-file summary of what was modified}

## Verification
- [ ] Build passes
- [ ] Tests pass
- [ ] Lint passes
- [ ] Schema validation passes

## Review
Verdict: {approve/request_changes/reject}
{Link to review artifact}

## Artifacts
- Plan: {artifact URL or path}
- Diff: {artifact URL or path}
- Verification: {artifact URL or path}
- Review: {artifact URL or path}

## Run Metadata
- Run ID: {uuid}
- Task Type: {type}
- Model: {primary model used}
- Duration: {total run time}
```

## Labels
Apply these GitHub labels to PRs:
- `foundry` — always present on Foundry-generated PRs
- `needs-human-review` — always present; Foundry never self-merges
- Task type label: `endpoint-build`, `bug-fix`, `refactor`, etc.
- If migration guard was triggered: `migration-review`

## Review Expectations
Foundry PRs always require human review before merge. The reviewer subagent's verdict is advisory. A human must confirm:
- The change is correct.
- The change is safe.
- The change matches the original intent.
