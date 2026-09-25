# UCF

**An experiment in persistent machine operation across changing state.**

UCF began as Unicorn Foundry, the execution side of a discontinued project called Unicorn. Unicorn explored how a changing environment could be made machine-legible through **signals → evidence → state → legibility**. UCF explored the complementary problem: once a machine has a representation of its current environment, how can it change that environment deliberately, determine what actually happened, and continue from the resulting state?

The original implementation was built around Claude and software-engineering workflows. The underlying systems question was broader:

> **What must exist around an intelligent model for it to remain coherent while the environment it operates in changes?**

UCF treats the model as a participant in the system, not the system itself.

## The Loop

```text
WORLD
  │
  ▼
OBSERVATION
  │
  ▼
EVIDENCE
  │
  ▼
STATE(t)
  │
  ▼
REASON / DECIDE
  │
  ▼
INTENT
  │
  ▼
PLAN
  │
  ▼
CONTROLLED EXECUTION
  │
  ▼
VERIFICATION / REVIEW
  │
  ▼
OUTCOME
  │
  ▼
STATE(t+1)
  └──────────────↻
```

The important object is the **state transition**.

A model may reason, plan, classify, review, or propose an action. UCF surrounds those capabilities with explicit state, typed transitions, isolated execution, deterministic verification, independent evaluation, durable artifacts, and event history.

That distinction can be summarized as:

**intelligence at an instant ≠ intelligence through time**

## Origin

UCF was originally implemented as **Unicorn Foundry**, an internal control plane for Unicorn Protocol.

The two projects explored opposite sides of one loop:

```text
Unicorn
signals → evidence → state → legibility

UCF / Unicorn Foundry
state → intent → plan → action → verification → transition
```

Together, the intended system was:

```text
world
  ↓
representation
  ↓
intelligence
  ↓
controlled action
  ↓
world'
  ↓
representation'
  ↻
```

Unicorn is no longer an active project. UCF is being preserved and generalized because the infrastructure problem it exposed is not specific to Unicorn.

This repository does **not** claim to implement a learned world model or a complete architecture for general intelligence. It is a software-systems experiment in maintaining coherent machine operation across observation, action, consequence, and time.

## What The Existing Implementation Actually Contains

The historical Foundry implementation already provides concrete machinery for this experiment:

- a typed run-state machine;
- isolated git worktrees for actions;
- structured planning artifacts;
- model/provider routing;
- deterministic build, test, lint, and schema verification;
- independent diff review;
- persistent run events and artifacts;
- PostgreSQL-backed run state;
- Redis-backed work queues;
- evidence and extraction contracts;
- evaluation infrastructure;
- deterministic hooks for policy enforcement;
- retry, cancellation, and failure states.

Some originally planned paths remain incomplete. In particular, parts of the extraction/batch pipeline are still Phase 1 stubs. The repository should therefore be read as a working experimental system with unfinished surfaces, not as a completed general architecture.

## Historical Implementation

The codebase still uses its original **Foundry** terminology and contains Unicorn-specific adapters, schemas, task types, and documentation. Those are retained for now because they are evidence of how the experiment emerged.

The current restructuring deliberately starts with the **conceptual boundary** before rewriting the runtime:

```text
historical implementation        generalized interpretation

Unicorn state             →      environment state
Unicorn canon             →      state/evidence contracts
Claude                    →      intelligence provider
Foundry run               →      controlled state transition
git worktree              →      isolated action environment
verification              →      transition validation
review                    →      independent evaluation
run artifacts             →      durable transition evidence
PR                        →      one possible action outcome
```

The long-term architecture should not require Claude, GitHub, source code, or Unicorn. Those are properties of the first implementation, not invariants of UCF.

## Architectural Invariants

1. **State is explicit.** The system should not depend on a model reconstructing its entire operating reality from a prompt.
2. **Actions produce transitions.** Work is understood as movement from a known state to a resulting state.
3. **Evidence survives inference.** Claims about what happened should remain traceable to observations and artifacts.
4. **Execution is controlled.** Intelligence proposes or performs actions inside explicit boundaries.
5. **Verification is separate from generation.** Producing an action and establishing that it worked are different operations.
6. **History is durable.** Meaningful transitions leave events and artifacts behind.
7. **Models are replaceable participants.** UCF should not depend conceptually on one provider, model family, or reasoning architecture.
8. **Continuity is a systems property.** Long-horizon coherence comes from the loop around intelligence as well as from intelligence itself.

## Current Direction

This repository is being reopened as UCF rather than maintained as an active Unicorn Foundry product.

A provider-neutral UCF foundation now lives alongside the historical Foundry runtime:

- `IntelligenceProvider` separates orchestration from a concrete model vendor;
- `ExecutionEnvironment` separates isolated execution from Git worktrees;
- provider-neutral transition contracts represent state, evidence, actions, observations, verification, and outcomes;
- `TransitionEngine` closes a state → action → observation → verification → outcome loop;
- `TransitionJournal` requires the verified outcome to survive the call;
- `FoundryTransitionRuntime` maps the historical planner, implementer, verifier, migration guard, worktree manager, and artifact store onto those interfaces;
- integration tests exercise that adapter with a real Git repository and real worktree isolation.

The abstraction is therefore exercised by the original machinery, not only by fakes. The remaining P0 boundary is **runtime convergence**: the backwards-compatible `RunEngine` still owns the old database/event/PR lifecycle and must delegate its core transition work to the UCF path. PR creation should become publication after an accepted transition rather than the definition of completion.

See [RETROSPECTIVE.md](RETROSPECTIVE.md) for the present-day interpretation, [docs/runtime-decoupling-audit.md](docs/runtime-decoupling-audit.md) for the migration map, and [docs/architecture.md](docs/architecture.md) for the original Foundry architecture specification.

## Repository Map

```text
UCf/
├── README.md                         # current UCF thesis and status
├── RETROSPECTIVE.md                  # historical interpretation boundary
├── CLAUDE.md                         # guidance for future agents/engineering
├── docs/
│   ├── ucf-architecture.md           # generalized architecture mapping
│   ├── runtime-decoupling-audit.md   # migration map and remaining coupling
│   └── architecture.md               # original Unicorn Foundry specification
├── foundry/
│   ├── contracts/
│   │   ├── transition_models.py      # state, evidence, action, outcome contracts
│   │   └── ...                       # historical Foundry contracts
│   ├── runtime/
│   │   ├── interfaces.py             # observer/planner/executor/verifier/journal
│   │   └── transition_engine.py      # provider-neutral state-transition loop
│   ├── adapters/
│   │   └── foundry_transition.py     # historical Foundry -> UCF capability bridge
│   ├── environments/
│   │   ├── base.py                   # ExecutionEnvironment contract
│   │   ├── git_worktree.py           # concrete execution environment adapter
│   │   └── git_observer.py           # explicit before/after Git state
│   ├── providers/
│   │   ├── base.py                   # IntelligenceProvider contract
│   │   └── claude_*.py               # historical/default Claude adapters
│   ├── orchestration/                # historical Foundry run machinery
│   ├── verification/                 # historical deterministic code verification
│   ├── git/                          # historical Git/PR action surface
│   ├── tasks/                        # historical Foundry task implementations
│   ├── db/                           # historical run persistence
│   └── storage/
│       └── transition_journal.py     # durable UCF outcome adapter
├── app/                              # historical FastAPI control plane
├── workers/                          # historical background workers
├── canon/                            # historical Unicorn domain contracts
├── hooks/                            # historical deterministic safeguards
├── tests/
│   └── unit/runtime/                 # provider-neutral transition-loop tests
└── .github/workflows/
    └── ucf-foundation.yml            # compile, lint, foundation + regression tests
```

The repository intentionally contains both the generalized UCF foundation and the historical Foundry implementation. The historical directories are not being renamed away until their behavior has been migrated through exercised UCF interfaces.

## Historical Foundry Runtime

The sections below document the original concrete runtime. They are retained because they show how the systems problem was first implemented; they should not be read as requirements of the generalized UCF architecture.

## Historical Foundry Task Types


| Task Type | Description | Model Routing |
|-----------|-------------|---------------|
| `endpoint_build` | Build new API endpoints in unicorn-app | Sonnet (plan/impl), Opus (review) |
| `feature_slice` | Implement feature slices across the stack | Sonnet (plan/impl), Opus (review) |
| `bug_fix` | Diagnose and fix bugs with regression tests | Sonnet (plan/impl), Opus (review) |
| `refactor` | Refactor code with safety verification | Sonnet (plan/impl), Opus (review) |
| `migration_plan` | Database migration planning and execution | Opus (plan/review/guard) |
| `architecture_review` | Architecture-level review and analysis | Opus (plan/review) |
| `review_diff` | Standalone independent diff review | Opus (review) |
| `extraction_batch` | Batch signal-to-event extraction | Sonnet (extract), Haiku (classify) |
| `evidence_classification` | Classify evidence strength levels | Haiku (classify) |
| `eval_run` | Run evaluation suites against model outputs | Sonnet (evaluate) |
| `canon_update` | Update shared schemas and domain docs | Opus (plan/review), Sonnet (impl) |

## Historical Foundry Run Lifecycle

```
queued → creating_worktree → planning → implementing → verifying
    → verification_passed → reviewing → pr_opened → completed
```

Failure states: `plan_failed`, `verification_failed`, `review_failed`, `cancelled`, `errored`

Failed runs in `plan_failed`, `verification_failed`, or `review_failed` can be retried (transitions back to `queued`). Any non-terminal run can be cancelled.

## Historical Foundry API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/health` | Health check |
| `POST` | `/v1/runs` | Submit a new task run |
| `GET` | `/v1/runs/{id}` | Get run status and metadata |
| `GET` | `/v1/runs/{id}/events` | Get run events (state transitions) |
| `GET` | `/v1/runs/{id}/artifacts` | List run artifacts |
| `POST` | `/v1/runs/{id}/cancel` | Cancel an in-progress run |
| `POST` | `/v1/runs/{id}/retry` | Retry a failed run |
| `POST` | `/v1/reviews` | Request an independent review |
| `POST` | `/v1/specs/plan` | Generate a plan from a spec |
| `POST` | `/v1/patches/apply` | Apply a patch to a worktree |
| `POST` | `/v1/batches/extract` | Start a batch extraction job |
| `GET` | `/v1/batches/{id}` | Get batch status |
| `GET` | `/v1/batches/{id}/results` | Get extraction results |
| `POST` | `/v1/evals/run` | Run an evaluation suite |
| `GET` | `/v1/evals/{id}` | Get eval results |
| `POST` | `/v1/worktrees/cleanup` | Clean up stale worktrees |

## Historical Foundry Subagents

| Agent | Role | Model |
|-------|------|-------|
| **Planner** | Produces structured `PlanArtifact` with file-level steps | Sonnet / Opus |
| **Backend Implementer** | Executes plans in Go (unicorn-app API) | Sonnet |
| **Frontend Implementer** | Executes plans in TypeScript (Next.js) | Sonnet |
| **Reviewer** | Independent diff review (never sees the plan) | Opus |
| **Extractor** | Signal-to-event structured extraction | Sonnet |
| **Migration Guard** | High-scrutiny review for migrations/auth/infra | Opus |
| **Repo Explorer** | Read-only codebase reconnaissance | Haiku |

## Historical Foundry Claude Code Skills

| Skill | Description |
|-------|-------------|
| `spec-to-plan` | Generate a structured implementation plan from a spec |
| `endpoint-generator` | Scaffold a new API endpoint end-to-end |
| `safe-refactor` | Refactor code with automatic verification |
| `review-diff` | Review any diff independently |
| `issue-to-pr` | Resolve a GitHub issue from triage to PR |
| `extract-signals` | Run signal extraction pipeline |
| `run-eval` | Execute evaluation suites |

## Historical Foundry Hooks (Deterministic Enforcement)

| Hook | Trigger | Purpose |
|------|---------|---------|
| `block_secrets.sh` | Pre: Read, Edit, Write | Block access to `.env`, `*.key`, `*secrets*`, etc. |
| `block_protected_paths.sh` | Pre: Edit, Write | Guard `migrations/`, `auth/`, `infra/`, Docker files |
| `require_plan.sh` | Pre: Edit, Write | Block edits without a stored plan |
| `verify_after_edit.sh` | Post: Edit, Write | Run verification after file modifications |
| `log_tool_call.sh` | Post: all tools | Log every tool invocation for auditability |

## Historical Foundry MCP Profiles

Runs can be scoped to specific MCP server access:

| Profile | Servers | Use Case |
|---------|---------|----------|
| `none` | — | Default, no external access |
| `github_only` | GitHub | Code builds, PR workflows |
| `github_postgres_readonly` | GitHub + Postgres (read-only) | Research with data access |
| `research_full` | GitHub + Postgres (read-only) | Full research capabilities |
| `app_build_minimal` | GitHub | Minimal build access |

## Historical Foundry Model Routing

| Model | Use Case |
|-------|----------|
| **Opus 4.6** | Architecture, critical planning, review, migration guard, red-teaming |
| **Sonnet 4.6** | Implementation, structured extraction, endpoint building, evals |
| **Haiku 4.5** | Classification, tagging, reconnaissance, simple preprocessing |

Routing is defined in `foundry/orchestration/model_router.py`. Override via `model_override` in task requests when justified.

## Historical Foundry Database Schema

PostgreSQL tables managed via Alembic:

| Table | Purpose |
|-------|---------|
| `runs` | Run lifecycle records (state, branch, PR URL, metadata) |
| `run_events` | State transition events with timing and token usage |
| `run_artifacts` | Artifact metadata (type, storage path, checksum) |
| `worktrees` | Git worktree tracking and cleanup state |
| `batch_jobs` | Batch extraction/processing jobs |
| `batch_items` | Individual items within batch jobs |
| `eval_runs` | Evaluation run records with metrics |
| `verification_results` | Deterministic verification step results |

## Prerequisites

- Python 3.12+
- Docker and Docker Compose
- Git

## Setup

```bash
# Start Postgres and Redis
docker compose up -d postgres redis

# Install dependencies
pip install -e ".[dev]"

# Run database migrations
alembic upgrade head

# Run the API server
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Or run everything via Docker:

```bash
export ANTHROPIC_API_KEY=<your-key>
export GITHUB_TOKEN=<your-token>
docker compose up
```

This starts the API server, run worker, and batch worker with shared Postgres and Redis.

The API is available at `http://localhost:8000`. Health check: `GET /v1/health`.

## Configuration

All settings use the `FOUNDRY_` env prefix (via pydantic-settings):

| Variable | Default | Description |
|----------|---------|-------------|
| `FOUNDRY_DATABASE_URL` | `postgresql+asyncpg://foundry:foundry@localhost:5432/foundry` | PostgreSQL connection |
| `FOUNDRY_REDIS_URL` | `redis://localhost:6379` | Redis connection |
| `FOUNDRY_ANTHROPIC_API_KEY` | — | Anthropic API key |
| `FOUNDRY_GITHUB_TOKEN` | — | GitHub token for PR operations |
| `FOUNDRY_MAX_CONCURRENT_RUNS` | `5` | Max parallel run executions |
| `FOUNDRY_MAX_RETRIES_PER_RUN` | `3` | Max retry attempts per run |
| `FOUNDRY_WORKTREE_BASE_PATH` | `/tmp/foundry-worktrees` | Worktree storage directory |
| `FOUNDRY_LOG_LEVEL` | `INFO` | Log verbosity |

## Development

```bash
# Run tests
pytest

# Lint and type check
ruff check .
mypy .

# Run a task via CLI
python scripts/run_task.py --type endpoint_build --spec "Add GET /v1/companies/{id}/timeline"

# Seed the database with test data
python scripts/seed_db.py

# Export artifacts for inspection
python scripts/export_artifacts.py --run-id <uuid>
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| API Framework | FastAPI 0.115+ |
| Data Validation | Pydantic 2.9+ |
| Database ORM | SQLAlchemy 2.0+ (async) |
| Database Driver | asyncpg |
| Migrations | Alembic |
| Task Queue | Redis 5.2+ |
| AI Provider | Anthropic SDK 0.40+ (Agent SDK, Messages API, Batch API) |
| HTTP Client | httpx |
| Object Storage | boto3 (S3-compatible) |
| Logging | python-json-logger |
| Build System | hatchling |
| Linting | ruff |
| Type Checking | mypy (strict mode) |
| Testing | pytest + pytest-asyncio |

## Historical Foundry Language Boundaries

- **Python** — this repo (Foundry). All orchestration, extraction, eval code.
- **Go** — unicorn-app backend. Foundry writes Go code into unicorn-app via PRs.
- **TypeScript** — unicorn-app frontend. Foundry writes TS code into unicorn-app via PRs.

Foundry never mixes languages. The appropriate implementer subagent is selected based on the target.

## License

Internal use only. Not licensed for external distribution.
