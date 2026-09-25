# Runtime Decoupling Audit

This audit separates the general UCF mechanism from assumptions inherited from
Unicorn Foundry and records which abstractions have been exercised by real
historical machinery.

## Current architecture

The repository now has three related layers:

1. **UCF foundation** — provider-neutral state, evidence, action, verification,
   outcome, environment, and journal contracts.
2. **Foundry adapter path** — the original Git/agent/verification/artifact
   machinery running through `TransitionEngine`.
3. **Historical RunEngine** — the backwards-compatible API/database/PR lifecycle
   that still owns the old `queued -> ... -> pr_opened -> completed` state machine.

The second layer is important: the general boundary is no longer proven only by
fakes.

## Generalized and exercised boundaries

### Intelligence provider

`AgentRunner` depends on `IntelligenceProvider`. Claude remains the default
historical backend, but provider identity is outside the UCF runtime contract.

### Execution environment and observation

`ExecutionEnvironment` owns workspace preparation and cleanup.
`GitWorktreeEnvironment` adapts the historical `WorktreeManager`.

`GitStateObserver` turns an actual Git workspace into explicit state containing
HEAD, dirty status, changed files, and a diff checksum. This supplies real
before/after state to the generic loop.

### Transition vocabulary and engine

`TransitionEngine` coordinates:

```text
state(t)
  -> plan
  -> controlled action
  -> observe
  -> verify / independently review
  -> durable outcome
  -> state(t+1)
```

The engine does not know about Claude, GitHub, Go, TypeScript, Unicorn, or pull
requests.

### Historical Foundry adapters

`foundry/adapters/foundry_transition.py` maps the original capabilities onto
that loop:

| Historical capability | UCF role |
| --- | --- |
| `TaskRequest` | `TransitionRequest` input |
| `AgentRunner.run_planner` | `TransitionPlanner` |
| `AgentRunner.run_implementer` | `ActionExecutor` |
| Git worktree | `ExecutionEnvironment` |
| Git HEAD/status/diff | `StateObserver` |
| `VerificationRunner` | deterministic verification |
| blind reviewer | independent transition evaluation |
| migration guard | shared protected-path verification policy |
| `ArtifactStore` | `TransitionJournal` |
| review/verification result | `TransitionOutcome` evidence |

`REQUEST_CHANGES` remains advisory in the adapter because that is the historical
Foundry behavior. `REJECT` and deterministic verification failure reject the
transition.

### Shared safety policy

Protected-path matching and migration-guard authorization now live in
`foundry/verification/policy.py`. Both `RunEngine` and the UCF adapter use the
same policy instead of maintaining parallel copies.

### Durable continuity

`ArtifactStoreTransitionJournal` persists
`transition_outcome.json` under the transition ID before workspace cleanup.
The resulting after-state can seed the next transition.

## Evidence

The adapter integration test creates a real temporary Git repository and uses
the real `WorktreeManager` and `GitStateObserver`. It then runs planning,
implementation, verification, blind review, journaling, and cleanup through
`TransitionEngine`.

Current CI evidence for this milestone:

- 21 targeted UCF / Foundry-adapter tests pass;
- 495 full-suite tests pass;
- compile and targeted Ruff checks pass.

## Remaining historical couplings

| Coupling | Current state | Desired boundary | Priority |
| --- | --- | --- | --- |
| Run lifecycle terminal | `PR_OPENED -> COMPLETED` still lives in `RunEngine` | verified `TransitionOutcome` defines operation result | P0 |
| Publication | PR creation is embedded in run lifecycle | publisher is post-transition / environment-specific | P0 |
| Runtime convergence | adapter path and `RunEngine` both exist | legacy engine delegates core transition work | P0 |
| Persistence | run/PR/worktree tables | transition/outcome/workspace records + legacy projection | P1 |
| Executor language | Go / TypeScript literal | executor capability selection | P1 |
| Verification | code-oriented Go/TS/schema dispatch | verifier plugins by environment/capability | P1 |
| Model routing | Claude model IDs | provider + capability routing | P1 |
| Prompts | coding-specific role prompts | environment-specific planner/executor adapters | P1 |
| Canon | Unicorn/startup schemas | environment-specific state contracts | P2 |
| Extraction | startup signal extraction | observer adapters | P2 |
| Config | `FOUNDRY_*`, Unicorn-era names | UCF names + compatibility aliases | P2 |
| API | `/runs`, `/patches`, `/worktrees` | transition/action/environment surfaces | P3 |

## Next P0 milestone: converge RunEngine

Do not delete or rename the historical state machine first. Make it a
compatibility projection over the UCF transition loop.

The next migration should:

1. let a legacy `TaskRequest` create a UCF `TransitionRequest`;
2. delegate plan -> execute -> observe -> verify -> journal to
   `FoundryTransitionRuntime`;
3. map a rejected `TransitionOutcome` into the existing failure states/events;
4. map an accepted outcome into the existing post-verification path;
5. treat PR creation as publication after an accepted transition, not as the
   definition of the transition itself;
6. preserve current API responses, database rows, artifacts, and event history
   while compatibility is required.

This is the point at which the two runtime paths actually converge.

## What should not be renamed yet

Do not mass-rename Foundry classes, database tables, routes, or artifact types
merely to match the new vocabulary. Generalization is being earned through
exercised interfaces and regression tests. Rename only when a replacement
boundary is in use.
