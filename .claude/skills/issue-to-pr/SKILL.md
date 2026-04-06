# SKILL.md — issue-to-pr

## Description
End-to-end: takes a GitHub issue or task description and drives it through the full Foundry run lifecycle to produce a PR.

## When to Use
- A GitHub issue is assigned to Foundry.
- A human submits a task with `open_pr: true`.
- Explicitly invoked via `/issue-to-pr`.

## Workflow

1. **Parse the issue.** Extract: title, description, acceptance criteria, labels, linked issues.

2. **Determine task type.** Based on labels and content:
   - `bug` label → `bug_fix`
   - `enhancement` label → `endpoint_build` or `feature_slice`
   - `refactor` label → `refactor`
   - `migration` label → `migration_plan`

3. **Create the run.** Submit to `POST /v1/runs` with the appropriate task type and metadata.

4. **Monitor the run.** Poll `GET /v1/runs/{id}` until terminal state.

5. **Report back.** If PR opened, comment on the issue with the PR link. If failed, comment with the failure reason and artifact links.

## Output
A PR on GitHub, or a failure report with artifacts.

## Constraints
- One issue = one run = one PR. Do not batch multiple issues.
- If the issue is underspecified, the planner will surface open questions. These should be reported back to the issue as a comment, not guessed at.
