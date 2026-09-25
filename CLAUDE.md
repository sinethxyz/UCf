# UCF — Project Guidance

## What This Repo Is

UCF is an experiment in persistent machine operation across changing state.

The repository now contains two layers:

- **UCF foundation** — provider-neutral contracts and a minimal transition runtime built around explicit state, evidence, action, verification, outcomes, and continuity.
- **Historical Foundry runtime** — the original Claude/Git/PR orchestration system built while working on the now-discontinued Unicorn project.

The historical implementation is evidence of how the experiment emerged. Preserve it, but do not treat Unicorn, Claude, GitHub, source code, or pull requests as architectural invariants of UCF.

The general loop is:

**State(t) → Reason/Plan → Controlled Action → Observation → Verification → Outcome → State(t+1)**

The important object is the state transition. The model is a participant in the loop, not the loop itself.

## Core Thesis

UCF explores the boundary between **intelligence at an instant** and **intelligence through time**.

New foundation work should preserve these invariants:

1. state is explicit;
2. evidence remains attached to claims about state and outcomes;
3. actions occur through controlled environment boundaries;
4. verification is separate from generation;
5. meaningful transitions leave durable history;
6. intelligence providers are replaceable;
7. resulting state can seed the next transition.

The original Unicorn chain — **Signals → Evidence → State → Legibility** — remains historical context, not the active product objective.

## Compatibility Rule

Do not mass-rename or delete historical Foundry code merely to make terminology look generic. Generalization must be earned through exercised interfaces and tests.

When touching new UCF foundation code, prefer the contracts under `foundry/contracts/transition_models.py`, `foundry/runtime/`, `foundry/environments/`, and `foundry/providers/base.py`.

When touching historical Foundry code, preserve existing behavior unless the task explicitly migrates that behavior onto the new transition interfaces.

## Non-Negotiable Rules

1. **Plan before implementing.** Every non-trivial change starts with a planning pass that produces a structured PlanArtifact (JSON). No implementation begins without a stored plan.

2. **Worktree isolation.** All code edits happen in git worktrees, never on main, never on a shared branch. One worktree per run.

3. **Verification before PR.** Every run must pass deterministic verification (build, test, lint, schema validation) before a PR is opened. No exceptions.

4. **Artifacts for everything.** Every meaningful run must store artifacts: plans, diffs, verification results, reviews, patches, PR metadata, error logs. If a run leaves no trace, something is broken.

5. **Never touch secrets.** Never read, write, or log files matching: `*.env`, `*.env.*`, `*secrets*`, `*credentials*`, `*.pem`, `*.key`, `*service-account*`. Hooks enforce this, but you must also never attempt it.

6. **Protected paths require authorization.** Files under `migrations/`, `auth/`, `infra/`, and Docker configs can only be modified by `migration_plan` or `canon_update` task types. Hooks enforce this.

7. **Reviewer independence.** The reviewer subagent must never see the plan. It judges the diff on its own merits. This prevents confirmation bias.

8. **Schema compliance.** All extraction outputs must validate against the canon JSON Schemas in `canon/schemas/`. Invalid output is a failure, not a best-effort result.

9. **Structured output over prose.** Plans, reviews, extractions, evals, and verification results must return validated JSON matching their defined schemas. Never return prose where structured output is expected.

10. **Do not introduce new provider coupling into the UCF foundation.** Claude remains the default provider for the historical Foundry runtime, but new transition/runtime interfaces must depend on capabilities rather than a model vendor.

## Repo Layout

```
unicorn-foundry/
├── CLAUDE.md                  ← you are here
├── .claude/                   ← settings, rules, agents, skills
├── .mcp.json                  ← MCP server connections
├── app/                       ← FastAPI control plane
├── foundry/                   ← orchestration core
│   ├── contracts/             ← Pydantic models (task, run, review, extraction, eval)
│   ├── db/                    ← SQLAlchemy models, Alembic migrations, queries
│   ├── orchestration/         ← run engine, agent runner, model router
│   ├── git/                   ← worktree manager, branch naming, PR creation
│   ├── providers/             ← Claude Agent SDK, Messages API, Batch API, GitHub
│   ├── tasks/                 ← task type implementations
│   ├── verification/          ← go, ts, schema verification runners
│   └── storage/               ← artifact + log storage
├── workers/                   ← background task consumers
├── hooks/                     ← deterministic enforcement scripts
├── evals/                     ← datasets, scorers, runner
├── canon/                     ← shared schemas + domain docs (source of truth)
├── artifacts/                 ← ephemeral local staging
├── scripts/                   ← CLI utilities
└── tests/                     ← unit + integration
```

## Historical Foundry Canon

The source of truth for the historical Unicorn domain model lives in `canon/`. It is not the general UCF state model.

Before doing any extraction, schema, or domain work, always read the relevant canon document:
- `canon/docs/event_taxonomy.md` — what counts as an event, event types, required fields
- `canon/docs/evidence_taxonomy.md` — evidence types, strength levels, attachment rules
- `canon/docs/state_model.md` — how company state is computed from events + evidence
- `canon/docs/scoring_methodology.md` — how scorecards work, what metrics matter

Canon schemas in `canon/schemas/` are the contract between Foundry and unicorn-app. When a schema changes, both repos must update.

## Model Routing

Use the right model for the right job:

- **Opus 4.6** — architecture, planning for critical systems, review, migration guard, red-teaming, thesis-level reasoning
- **Sonnet 4.6** — implementation, structured extraction, endpoint building, evals, medium-complexity tasks
- **Haiku 4.5** — classification, tagging, reconnaissance, simple preprocessing, cost-sensitive bulk work

Default routing is defined in `foundry/orchestration/model_router.py`. Override via `model_override` in task requests only when justified.

## Historical Foundry Language Boundaries

- **Go** — unicorn-app backend (API, workers). When implementing Go code, follow the patterns already in `services/api/`.
- **TypeScript** — unicorn-app frontend (Next.js). Follow patterns in `apps/web/`.
- **Python** — this repo (Foundry). All orchestration, extraction, eval code.

Never mix these. A task that touches Go code uses the backend-implementer subagent. A task that touches TS uses the frontend-implementer. Foundry itself is always Python.

## Historical Foundry Run Lifecycle

1. A task is submitted via the control plane API.
2. A worktree is created for the target repo + branch.
3. The planner subagent produces a structured plan.
4. The appropriate implementer subagent executes the plan in the worktree.
5. Deterministic verification runs (build, test, lint, schema).
6. The reviewer subagent independently reviews the diff.
7. If approved, a PR is opened. If not, the run fails with a review artifact.
8. All artifacts are stored. All events are logged.

## Writing Code in This Repo

When modifying Foundry itself:
- All Pydantic models go in `foundry/contracts/`.
- All database queries go in `foundry/db/queries/`.
- All orchestration logic goes in `foundry/orchestration/`.
- All provider integrations go in `foundry/providers/`.
- All task-specific logic goes in `foundry/tasks/`.
- Tests mirror the source structure under `tests/`.
- Use type hints everywhere. No `Any` without justification.
- Docstrings on public functions and classes.

## What You Must Never Do

- Never commit directly to main.
- Never skip verification.
- Never return prose where JSON is expected.
- Never access unicorn-app's database directly.
- Never deploy anything.
- Never store secrets in code, logs, or artifacts.
- Never modify canon schemas without opening a corresponding PR against unicorn-app.
