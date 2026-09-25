# Runtime Decoupling Audit

This audit separates the general UCF mechanism from assumptions inherited from Unicorn Foundry.

## Already generalized in this branch

### Intelligence provider boundary

`AgentRunner` now depends on an `IntelligenceProvider` protocol. Claude remains the default historical implementation, but the orchestration boundary no longer requires the concrete Claude provider type.

### Execution target boundary

`TaskRequest.repo` remains named for backwards compatibility, but it is no longer restricted to `unicorn-app` or `unicorn-foundry`.

### Environment boundary

`ExecutionEnvironment` defines prepare, observe-changes, and cleanup operations. `GitWorktreeEnvironment` adapts the historical worktree implementation to that interface.

### Transition vocabulary

`foundry/contracts/transition_models.py` defines provider-neutral state snapshots, evidence references, transition requests, observations, and outcomes without assuming GitHub or Unicorn.

## Remaining historical couplings

| Coupling | Current form | General form | Migration priority |
| --- | --- | --- | --- |
| Lifecycle terminal | `PR_OPENED -> COMPLETED` | outcome recorded / accepted | P0 |
| Action environment | Git worktree | ExecutionEnvironment | P0 |
| Action result | Git diff + PR | environment-specific action artifact | P0 |
| Implementer role | Go / TypeScript literal | executor capability | P1 |
| Verification | Go/TS/schema commands | verifier plugins | P1 |
| Model routing | Claude model IDs | provider + capability routing | P1 |
| Prompt layer | coding-specific planner/implementer prompts | transition-role prompts | P1 |
| Canon | Unicorn/startup schemas | environment-specific state contracts | P2 |
| Extraction | startup signal extraction | observer adapters | P2 |
| Config names | FOUNDRY, unicorn_app_* | UCF + legacy aliases | P2 |
| Persistence names | runs, PR URL, worktrees | transitions, outcomes, workspaces | P3 |
| API routes | /runs, /patches, /worktrees | /transitions, /actions, /environments | P3 |

## P0 migration: close the generic loop

The next runtime milestone should prove one transition that does not know about Unicorn and does not require the run engine to understand GitHub.

Required boundaries:

1. `ExecutionEnvironment.prepare()`
2. provider-assisted planning/reasoning
3. environment-specific execution
4. `ExecutionEnvironment.observe_changes()`
5. verifier/evaluator result
6. durable `TransitionOutcome`
7. state snapshot for the next transition

The historical Git/PR workflow can then become one adapter exercising that loop.

## What should not be renamed yet

Do not mass-rename Foundry classes, database tables, routes, or artifact types merely to match the new vocabulary. Renaming before the generalized loop works would create churn without increasing capability.

Keep the historical runtime operational while new interfaces are introduced alongside it. Once a non-Unicorn closed loop passes end to end, migrate internals incrementally.

## Acceptance test for UCF vNext foundation

The generalized foundation is real when a test can:

- create a `TransitionRequest` for a non-Unicorn environment;
- inject a fake intelligence provider;
- inject a fake execution environment;
- execute a state transition without Claude, Git, GitHub, Go, TypeScript, or Unicorn;
- produce evidence plus a durable `TransitionOutcome`;
- use the resulting state as the input to the next transition.

Until that exists, UCF is conceptually generalized but operationally still Foundry.
