# Unicorn Foundry

Internal Claude orchestration system for [Unicorn Protocol](https://github.com/sinethxyz/UCf). Foundry plans, builds, reviews, extracts, evaluates, and improves the Unicorn system.

Foundry is **not** a chatbot. It is a controlled run engine that produces artifacts, diffs, PRs, and structured data.

## Core Thesis

Unicorn Protocol makes startup reality computationally legible.

**Signals → Evidence → State → Legibility**

A startup emits signals. Those signals become evidence. Evidence is used to infer state. State becomes legible to humans and software. Everything Foundry builds serves that chain.

## Architecture

Two repos, strict separation:

| Repo | Purpose | Stack |
|------|---------|-------|
| `unicorn-app` | The product. Users touch this. | Next.js + Go + Postgres |
| `unicorn-foundry` | The build system. This repo. | Python + FastAPI + Claude |

Foundry writes code **into** unicorn-app via git worktrees and PRs. It never writes to unicorn-app's database directly. It never deploys anything.

## Repository Structure

```
unicorn-foundry/
├── CLAUDE.md                  # Project guidance and non-negotiable rules
├── .claude/                   # Claude Code configuration
│   ├── settings.json          # Permissions, hooks, context files
│   ├── agents/                # Subagent definitions (planner, reviewer, etc.)
│   ├── rules/                 # Enforcement rules (safety, contracts, testing)
│   └── skills/                # Skill definitions (spec-to-plan, endpoint-generator, etc.)
├── .mcp.json                  # MCP server connections
├── app/                       # FastAPI control plane
│   ├── main.py                # Application entry point
│   ├── config.py              # Environment configuration
│   ├── deps.py                # Dependency injection
│   └── routes/                # API route handlers
├── foundry/                   # Orchestration core
│   ├── contracts/             # Pydantic models (task, run, review, extraction, eval)
│   ├── db/                    # SQLAlchemy models, queries
│   ├── orchestration/         # Run engine, agent runner, model router
│   ├── git/                   # Worktree manager, branch naming, PR creation
│   ├── providers/             # Claude Agent SDK, Messages API, Batch API, GitHub
│   ├── tasks/                 # Task type implementations
│   ├── verification/          # Go, TypeScript, schema verification runners
│   └── storage/               # Artifact and log storage
├── workers/                   # Background task consumers
├── hooks/                     # Deterministic enforcement scripts
├── evals/                     # Datasets, scorers, eval runner
├── canon/                     # Shared schemas and domain docs (source of truth)
├── artifacts/                 # Ephemeral local artifact staging
├── scripts/                   # CLI utilities
├── tests/                     # Unit and integration tests
├── docs/                      # Architecture specification
├── pyproject.toml
├── Dockerfile
└── docker-compose.yml
```

## How Runs Work

Every Foundry operation follows a controlled lifecycle:

1. A task is submitted via the control plane API (`POST /v1/runs`).
2. A git worktree is created for the target repo and branch.
3. The **planner** subagent produces a structured implementation plan.
4. The appropriate **implementer** subagent executes the plan in the worktree.
5. **Deterministic verification** runs (build, test, lint, schema validation).
6. The **reviewer** subagent independently reviews the diff (without seeing the plan).
7. If approved, a PR is opened. If not, the run fails with a review artifact.
8. All artifacts are stored. All events are logged.

## Task Types

| Task Type | Model | Output |
|-----------|-------|--------|
| `endpoint_build` | Sonnet 4.6 | plan + diff + PR |
| `feature_slice` | Sonnet 4.6 | plan + diff + PR |
| `bug_fix` | Sonnet 4.6 | plan + diff + PR |
| `refactor` | Sonnet 4.6 | plan + diff + PR |
| `migration_plan` | Opus 4.6 | plan artifact only |
| `review_diff` | Opus 4.6 | review verdict |
| `extraction_batch` | Haiku 4.5 / Sonnet 4.6 | structured JSON |
| `eval_run` | Sonnet 4.6 | eval results |

## Model Routing

- **Opus 4.6** — architecture, planning, review, migration guard, red-teaming
- **Sonnet 4.6** — implementation, structured extraction, evals
- **Haiku 4.5** — classification, tagging, reconnaissance, bulk work

## Quick Start

```bash
# Start all services
docker compose up -d

# Health check
curl http://localhost:8000/v1/health

# Submit a task (once implemented)
python scripts/run_task.py \
  --task-type endpoint_build \
  --repo unicorn-app \
  --title "Add timeline endpoint" \
  --prompt "Build GET /v1/companies/{id}/timeline"
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/health` | Service health check |
| `POST` | `/v1/runs` | Submit a new task |
| `GET` | `/v1/runs/{id}` | Get run status |
| `POST` | `/v1/runs/{id}/cancel` | Cancel a run |
| `POST` | `/v1/runs/{id}/retry` | Retry a failed run |
| `GET` | `/v1/runs/{id}/events` | List run events |
| `GET` | `/v1/runs/{id}/artifacts` | List run artifacts |
| `POST` | `/v1/reviews` | Submit a diff for review |
| `POST` | `/v1/specs/plan` | Convert spec to plan |
| `POST` | `/v1/batches/extract` | Submit batch extraction |
| `GET` | `/v1/batches/{id}` | Get batch status |
| `POST` | `/v1/evals/run` | Run an evaluation |
| `GET` | `/v1/evals/{id}` | Get eval results |
| `POST` | `/v1/worktrees/cleanup` | Clean stale worktrees |

## Development

```bash
# Install dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check .

# Type check
mypy .
```

## Non-Negotiable Rules

1. Plan before implementing. No implementation without a stored plan.
2. All code edits happen in worktrees, never on main.
3. Verification before PR. No exceptions.
4. Every run must produce stored artifacts.
5. Never touch secrets or credential files.
6. Protected paths (migrations, auth, infra) require explicit task authorization.
7. Reviewer subagent must never see the plan.
8. Extraction outputs must validate against canon JSON Schemas.
9. Structured output over prose — always.
10. No Claude in the hot path. The app serves precomputed truth.

## Documentation

- [Architecture Specification](docs/architecture.md) — complete system design
- [CLAUDE.md](CLAUDE.md) — project guidance for Claude
