# SKILL.md — spec-to-plan

## Description
Converts a feature specification or task description into a structured implementation plan.

## When to Use
- User provides a feature spec, bug report, or describes work to be done.
- A Foundry run begins and needs a planning pass.
- Explicitly invoked via `/spec-to-plan`.

## Workflow

1. **Parse the spec.** Extract: objective, constraints, affected domains, acceptance criteria.

2. **Explore the repo.** Call the `repo-explorer` subagent on the target area to discover current structure, patterns, and conventions.

3. **Identify all affected files.** For each change:
   - Determine if the file exists (modify) or needs creation (create).
   - Determine dependencies between files (e.g., model before handler, handler before route registration).

4. **Check contracts.** Read relevant OpenAPI specs and JSON Schemas to ensure the plan aligns with existing contracts. If contracts need updating, include those as plan steps.

5. **Assess complexity.** Based on file count, domain count, and risk factors:
   - 1-3 files, single domain → `small`
   - 4-10 files, single domain → `medium`
   - 10+ files or cross-domain → `large`
   - Migrations, auth, infra → `critical`

6. **Identify risks.** What could go wrong? Missing indexes, backwards-incompatible changes, performance implications, missing test coverage.

7. **Surface open questions.** If the spec is ambiguous, list what needs clarification rather than guessing.

8. **Produce PlanArtifact.** Validated JSON with ordered steps, dependencies, risks, open questions, and complexity estimate.

## Output
PlanArtifact JSON validated against `foundry/contracts/task_types.py::PlanArtifact`.

## Failure Conditions
- Spec is too vague to produce a concrete plan → return plan with `open_questions` populated and `estimated_complexity: null`.
- Target area of the repo has no discoverable patterns → report this in `risks`.
