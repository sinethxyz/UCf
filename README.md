# Unicorn Foundry

Internal Claude orchestration system for [Unicorn Protocol](https://github.com/sinethxyz/ucf). Plans, builds, reviews, extracts, evaluates, and improves the Unicorn system through controlled, artifact-producing runs.

Foundry is not a chatbot. It is a **controlled run engine** that produces artifacts, diffs, PRs, and structured data.

## How It Works

1. A task is submitted via the control plane API.
2. A git worktree is created for the target repo and branch.
3. A **planner** subagent produces a structured plan.
4. An **implementer** subagent executes the plan in the worktree.
5. Deterministic **verification** runs (build, test, lint, schema validation).
6. A **reviewer** subagent independently reviews the diff.
7. If approved, a PR is opened. All artifacts are stored.

Every operation is isolated, logged, and reproducible.

## Architecture

```
External Inputs (specs, sources, bug reports, eval datasets)
                        │
                        ▼
              ┌─────────────────┐
              │  FastAPI Control │  POST /v1/runs, /v1/reviews,
              │     Plane       │  /v1/batches, /v1/evals, ...
              └────────┬────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
    Orchestrator   Batch Proc   Eval Runner
    (Agent SDK)    (Messages)   (Messages)
          │            │            │
          ▼            ▼            ▼
              Claude Layer
    (agents, skills, hooks, rules)
                       │
                       ▼
              Foundry Storage
    (PostgreSQL, Redis, artifact store)
                       │
                       ▼
              unicorn-app (via PRs)
```

## Repo Structure

```
unicorn-foundry/
├── CLAUDE.md                  # repo-wide guidance
├── .claude/                   # Claude configuration
│   ├── settings.json
│   ├── agents/                # planner, implementers, reviewer, etc.
│   ├── rules/                 # repo-safety, api-contracts, testing, pr-standards
│   └── skills/                # spec-to-plan, endpoint-generator, etc.
├── app/                       # FastAPI control plane
│   └── routes/                # runs, reviews, specs, batches, evals, etc.
├── foundry/                   # orchestration core
│   ├── contracts/             # Pydantic models
│   ├── db/                    # SQLAlchemy models, Alembic migrations, queries
│   ├── orchestration/         # run engine, agent runner, model router
│   ├── git/                   # worktree manager, branch naming, PR creation
│   ├── providers/             # Claude Agent SDK, Messages API, Batch API, GitHub
│   ├── tasks/                 # task type implementations
│   ├── verification/          # Go, TS, schema verification runners
│   └── storage/               # artifact + log storage
├── workers/                   # background task consumers
├── hooks/                     # deterministic enforcement scripts
├── evals/                     # datasets, scorers, runner
├── canon/                     # shared schemas + domain docs (source of truth)
├── artifacts/                 # ephemeral local staging
├── scripts/                   # CLI utilities
├── tests/                     # unit + integration
└── docs/                      # architecture spec
```

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

# Run the API server
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Or run everything via Docker:

```bash
export ANTHROPIC_API_KEY=<your-key>
export GITHUB_TOKEN=<your-token>
docker compose up
```

The API is available at `http://localhost:8000`. Health check: `GET /v1/health`.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/runs` | Submit a new task run |
| `GET` | `/v1/runs/{id}` | Get run status and metadata |
| `GET` | `/v1/runs/{id}/events` | Stream run events |
| `GET` | `/v1/runs/{id}/artifacts` | List run artifacts |
| `POST` | `/v1/reviews` | Request an independent review |
| `POST` | `/v1/specs/plan` | Generate a plan from a spec |
| `POST` | `/v1/patches/apply` | Apply a patch to a worktree |
| `POST` | `/v1/batches/extract` | Start a batch extraction job |
| `GET` | `/v1/batches/{id}` | Get batch status |
| `POST` | `/v1/evals/run` | Run an evaluation suite |
| `GET` | `/v1/evals/{id}` | Get eval results |
| `POST` | `/v1/worktrees/cleanup` | Clean up stale worktrees |

## Model Routing

| Model | Use Case |
|-------|----------|
| Opus 4.6 | Architecture, planning, review, migration guard, red-teaming |
| Sonnet 4.6 | Implementation, extraction, endpoint building, evals |
| Haiku 4.5 | Classification, tagging, recon, simple preprocessing |

## Development

```bash
# Run tests
pytest

# Lint and type check
ruff check .
mypy .

# Run a task via CLI
python scripts/run_task.py --type endpoint_build --spec "Add GET /v1/companies/{id}/timeline"
```

## Core Thesis

Unicorn Protocol makes startup reality computationally legible.

**Signals -> Evidence -> State -> Legibility**

A startup emits signals. Those signals become evidence. Evidence is used to infer state. State becomes legible to humans and software. Everything Foundry builds serves that chain.

## License

Internal use only. Not licensed for external distribution.
