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

The immediate goal is to preserve the original implementation, separate its general mechanisms from Unicorn-specific assumptions, and make the experiment legible before changing its runtime architecture.

See [RETROSPECTIVE.md](RETROSPECTIVE.md) for the present-day interpretation of the experiment and [docs/architecture.md](docs/architecture.md) for the original Foundry architecture specification.

## Repo Structure

```
unicorn-foundry/
├── CLAUDE.md                          # repo-wide guidance and non-negotiable rules
├── .claude/
│   ├── settings.json                  # permissions, hooks, deny rules
│   ├── agents/                        # subagent definitions
│   │   ├── planner.md                 # structured implementation planning
│   │   ├── backend-implementer.md     # Go implementation specialist
│   │   ├── frontend-implementer.md    # TypeScript/Next.js specialist
│   │   ├── reviewer.md               # independent diff reviewer
│   │   ├── extractor.md              # signal-to-event extraction
│   │   ├── migration-guard.md        # high-scrutiny infra/migration review
│   │   └── repo-explorer.md          # read-only reconnaissance
│   ├── rules/                         # enforced policy documents
│   │   ├── repo-safety.md            # secret blocking, protected paths
│   │   ├── api-contracts.md          # OpenAPI-first, schema validation
│   │   ├── testing.md               # test requirements per change type
│   │   ├── pr-standards.md          # PR format, labels, artifact links
│   │   └── migrations.md           # migration safety, forbidden operations
│   └── skills/                        # reusable Claude Code skills
│       ├── spec-to-plan/              # generate plans from specs
│       ├── endpoint-generator/        # scaffold API endpoints
│       ├── safe-refactor/             # refactor with verification
│       ├── review-diff/               # review any diff
│       ├── issue-to-pr/               # end-to-end issue resolution
│       ├── extract-signals/           # signal extraction pipeline
│       └── run-eval/                  # run evaluation suites
├── .mcp.json                          # MCP server connections (GitHub, Postgres)
├── app/                               # FastAPI control plane
│   ├── main.py                        # app entry, middleware, router registration
│   ├── config.py                      # env-based settings (FOUNDRY_ prefix)
│   ├── deps.py                        # dependency injection
│   └── routes/
│       ├── runs.py                    # run CRUD, cancel, retry
│       ├── reviews.py                 # independent review requests
│       ├── specs.py                   # spec-to-plan generation
│       ├── patches.py                 # patch application to worktrees
│       ├── batches.py                 # batch extraction jobs
│       ├── evals.py                   # evaluation suite runs
│       ├── worktrees.py              # worktree cleanup
│       └── health.py                 # health check
├── foundry/                           # orchestration core
│   ├── contracts/                     # Pydantic models (strict, typed)
│   │   ├── shared.py                 # TaskType, RunState, MCPProfile, enums
│   │   ├── task_types.py             # TaskRequest, PlanStep, PlanArtifact
│   │   ├── run_models.py            # RunEvent, RunArtifact, RunResponse
│   │   ├── review_models.py         # ReviewIssue, ReviewVerdict
│   │   ├── extraction_models.py     # Evidence, ExtractionEvent, ExtractionResult
│   │   └── eval_models.py           # EvalDefinition, EvalItemResult, EvalResult
│   ├── db/
│   │   ├── engine.py                 # async SQLAlchemy engine setup
│   │   ├── models.py                # ORM: Run, RunEvent, RunArtifact, Worktree,
│   │   │                            #       BatchJob, BatchItem, EvalRun,
│   │   │                            #       VerificationResult
│   │   └── queries/                  # data access layer
│   │       ├── runs.py              # run CRUD queries
│   │       ├── artifacts.py         # artifact storage queries
│   │       ├── batches.py           # batch job queries
│   │       └── evals.py            # eval run queries
│   ├── orchestration/
│   │   ├── run_engine.py            # core state machine (14 states, transitions)
│   │   ├── agent_runner.py          # Agent SDK wrapper for subagents
│   │   ├── model_router.py          # task-type → agent-role → model mapping
│   │   └── prompt_templates.py      # system prompts per agent/task
│   ├── git/
│   │   ├── worktree.py              # create, list, cleanup worktrees
│   │   ├── branch.py                # foundry/{task-type}-{description} naming
│   │   └── pr.py                    # PR creation via GitHub API
│   ├── providers/
│   │   ├── claude_agent.py          # Claude Agent SDK integration
│   │   ├── claude_messages.py       # Claude Messages API integration
│   │   ├── claude_batch.py          # Claude Message Batches API (bulk extraction)
│   │   └── github.py                # GitHub REST client (PRs, comments, labels)
│   ├── tasks/                         # task type implementations
│   │   ├── endpoint_build.py         # build new API endpoints
│   │   ├── feature_slice.py          # implement feature slices
│   │   ├── bug_fix.py                # diagnose and fix bugs
│   │   ├── refactor.py               # code refactoring
│   │   ├── migration_plan.py         # database migration planning
│   │   ├── extraction_batch.py       # batch signal extraction
│   │   ├── eval_run.py               # evaluation suite execution
│   │   └── review_diff.py            # standalone diff review
│   ├── verification/
│   │   ├── runner.py                 # dispatch verification by file type
│   │   ├── go_verify.py              # go build, go vet, go test
│   │   ├── ts_verify.py              # tsc, eslint, next build
│   │   └── schema_verify.py          # OpenAPI + JSON Schema validation
│   └── storage/
│       ├── artifact_store.py         # write/read artifacts to object storage
│       └── log_store.py              # structured run event logging
├── workers/                           # background task consumers
│   ├── run_worker.py                 # picks tasks from Redis, executes runs
│   ├── batch_worker.py               # polls Anthropic Batch API, stores results
│   └── cleanup_worker.py             # periodic worktree/artifact cleanup
├── hooks/                             # deterministic enforcement scripts
│   ├── pre_tool_use/
│   │   ├── block_secrets.sh          # deny read/write to secret files
│   │   ├── block_protected_paths.sh  # guard migrations/, auth/, infra/
│   │   └── require_plan.sh           # block edits without a stored plan
│   └── post_tool_use/
│       ├── verify_after_edit.sh      # run verification after file edits
│       └── log_tool_call.sh          # log every tool invocation
├── evals/                             # evaluation framework
│   ├── runner.py                     # eval orchestration
│   └── scorers/
│       ├── extraction_scorer.py      # score extraction accuracy
│       ├── evidence_scorer.py        # score evidence quality
│       └── state_scorer.py           # score state inference
├── canon/                             # source of truth (shared with unicorn-app)
│   ├── docs/                         # domain documentation
│   └── schemas/                      # JSON Schemas for domain objects
├── scripts/
│   ├── run_task.py                   # CLI task submission
│   ├── seed_db.py                    # seed database with test data
│   └── export_artifacts.py           # export artifacts for inspection
├── tests/                             # unit + integration tests
├── docs/
│   └── architecture.md               # full architecture specification
├── Dockerfile                         # Python 3.12-slim production image
├── docker-compose.yml                 # Postgres, Redis, app, workers
└── pyproject.toml                     # dependencies, ruff, mypy, pytest config
```

## Task Types

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

## Run Lifecycle

```
queued → creating_worktree → planning → implementing → verifying
    → verification_passed → reviewing → pr_opened → completed
```

Failure states: `plan_failed`, `verification_failed`, `review_failed`, `cancelled`, `errored`

Failed runs in `plan_failed`, `verification_failed`, or `review_failed` can be retried (transitions back to `queued`). Any non-terminal run can be cancelled.

## API Endpoints

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

## Subagents

| Agent | Role | Model |
|-------|------|-------|
| **Planner** | Produces structured `PlanArtifact` with file-level steps | Sonnet / Opus |
| **Backend Implementer** | Executes plans in Go (unicorn-app API) | Sonnet |
| **Frontend Implementer** | Executes plans in TypeScript (Next.js) | Sonnet |
| **Reviewer** | Independent diff review (never sees the plan) | Opus |
| **Extractor** | Signal-to-event structured extraction | Sonnet |
| **Migration Guard** | High-scrutiny review for migrations/auth/infra | Opus |
| **Repo Explorer** | Read-only codebase reconnaissance | Haiku |

## Claude Code Skills

| Skill | Description |
|-------|-------------|
| `spec-to-plan` | Generate a structured implementation plan from a spec |
| `endpoint-generator` | Scaffold a new API endpoint end-to-end |
| `safe-refactor` | Refactor code with automatic verification |
| `review-diff` | Review any diff independently |
| `issue-to-pr` | Resolve a GitHub issue from triage to PR |
| `extract-signals` | Run signal extraction pipeline |
| `run-eval` | Execute evaluation suites |

## Hooks (Deterministic Enforcement)

| Hook | Trigger | Purpose |
|------|---------|---------|
| `block_secrets.sh` | Pre: Read, Edit, Write | Block access to `.env`, `*.key`, `*secrets*`, etc. |
| `block_protected_paths.sh` | Pre: Edit, Write | Guard `migrations/`, `auth/`, `infra/`, Docker files |
| `require_plan.sh` | Pre: Edit, Write | Block edits without a stored plan |
| `verify_after_edit.sh` | Post: Edit, Write | Run verification after file modifications |
| `log_tool_call.sh` | Post: all tools | Log every tool invocation for auditability |

## MCP Profiles

Runs can be scoped to specific MCP server access:

| Profile | Servers | Use Case |
|---------|---------|----------|
| `none` | — | Default, no external access |
| `github_only` | GitHub | Code builds, PR workflows |
| `github_postgres_readonly` | GitHub + Postgres (read-only) | Research with data access |
| `research_full` | GitHub + Postgres (read-only) | Full research capabilities |
| `app_build_minimal` | GitHub | Minimal build access |

## Model Routing

| Model | Use Case |
|-------|----------|
| **Opus 4.6** | Architecture, critical planning, review, migration guard, red-teaming |
| **Sonnet 4.6** | Implementation, structured extraction, endpoint building, evals |
| **Haiku 4.5** | Classification, tagging, reconnaissance, simple preprocessing |

Routing is defined in `foundry/orchestration/model_router.py`. Override via `model_override` in task requests when justified.

## Database Schema

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

## Language Boundaries

- **Python** — this repo (Foundry). All orchestration, extraction, eval code.
- **Go** — unicorn-app backend. Foundry writes Go code into unicorn-app via PRs.
- **TypeScript** — unicorn-app frontend. Foundry writes TS code into unicorn-app via PRs.

Foundry never mixes languages. The appropriate implementer subagent is selected based on the target.

## License

Internal use only. Not licensed for external distribution.
