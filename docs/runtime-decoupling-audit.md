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

`foundry/contracts/transition_models.py` defines provider-neutral state snapshots, evidence references, action proposals, transition requests, observations, verification decisions, and outcomes without assuming GitHub or Unicorn.

### Generic transition loop

`TransitionEngine` now coordinates a minimal provider-neutral loop through injected observer, planner, executor, verifier, environment, and journal capabilities. The engine does not know about Claude, GitHub, Go, TypeScript, or Unicorn.

The historical `RunEngine` is still unchanged and Git/PR-shaped. The new engine is a parallel foundation, not a claim that migration is complete.

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

## P0 foundation status

The generic loop now exists alongside Foundry:

1. an execution environment prepares and cleans up an isolated workspace;
2. an observer establishes explicit before-state;
3. a planner proposes a provider-neutral action;
4. an executor applies the action;
5. the observer establishes after-state;
6. an independent verifier accepts or rejects the transition;
7. a journal records the verified outcome;
8. the resulting state can seed the next transition.

`tests/unit/runtime/test_transition_engine.py` exercises this with a non-Unicorn environment and fake capabilities.

The next P0 task is **adapter migration**: make the historical Git/Claude workflow exercise these interfaces rather than maintaining a separate architectural path. In particular, `PR_OPENED -> COMPLETED` must stop being the general definition of a successful transition.

## What should not be renamed yet

Do not mass-rename Foundry classes, database tables, routes, or artifact types merely to match the new vocabulary. Renaming before the generalized loop works would create churn without increasing capability.

Keep the historical runtime operational while new interfaces are introduced alongside it. Once a non-Unicorn closed loop passes end to end, migrate internals incrementally.

## Foundation boundary

The repository now contains the code-level boundary required to test UCF independently from Unicorn. Because the historical runtime is not yet routed through `TransitionEngine`, the project is currently in a dual state:

- **general UCF foundation:** provider/environment/transition interfaces plus a minimal loop;
- **historical Foundry runtime:** the working Git/PR orchestration implementation.

The next milestone is to make those two paths converge without erasing the original implementation history.
