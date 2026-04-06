# Unicorn Foundry — Complete Architecture Specification

## 1. Objective

Define `unicorn-foundry` as a real internal platform: the Claude-powered orchestration system that plans, builds, reviews, extracts, evaluates, and improves Unicorn Protocol. This document specifies every subsystem, contract, lifecycle, and file needed to stand it up.

---

## 2. System Identity

Foundry is **not** a chatbot wrapper. It is a **controlled run engine** with three jobs:

1. **Build Unicorn** — plan, implement, review, and ship code into `unicorn-app` via PRs.
2. **Extract reality** — ingest raw startup signals at scale, normalize them into structured events/evidence, and feed them into the product data pipeline.
3. **Evaluate quality** — run scoring evals, evidence-strength audits, and extraction accuracy checks.

Every operation is isolated, logged, artifact-producing, and reproducible.

---

## 3. Whole-System Diagram

```
                    ┌─────────────────────────────────────────┐
                    │            EXTERNAL INPUTS               │
                    │                                           │
                    │  human specs   raw sources   bug reports  │
                    │  eval datasets   canon updates            │
                    └──────────────────┬──────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                          unicorn-foundry                                 │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │                    FastAPI Control Plane                           │  │
│  │                                                                    │  │
│  │  POST /v1/runs          GET /v1/runs/{id}                         │  │
│  │  POST /v1/runs/{id}/cancel   POST /v1/runs/{id}/retry            │  │
│  │  GET  /v1/runs/{id}/events   GET  /v1/runs/{id}/artifacts        │  │
│  │  POST /v1/reviews       POST /v1/specs/plan                       │  │
│  │  POST /v1/patches/apply POST /v1/batches/extract                  │  │
│  │  GET  /v1/batches/{id}  GET  /v1/batches/{id}/results            │  │
│  │  POST /v1/evals/run     GET  /v1/evals/{id}                      │  │
│  │  POST /v1/worktrees/cleanup   GET /v1/health                     │  │
│  └────────────────────────┬───────────────────────────────────────────┘  │
│                           │                                              │
│            ┌──────────────┼──────────────┐                               │
│            ▼              ▼              ▼                                │
│  ┌──────────────┐ ┌─────────────┐ ┌──────────────┐                      │
│  │ Orchestrator │ │   Batch     │ │   Eval       │                      │
│  │              │ │  Processor  │ │  Runner      │                      │
│  │ Agent SDK    │ │  Messages   │ │  Messages    │                      │
│  │ (agentic)    │ │  API+Batch  │ │  API+Batch   │                      │
│  └──────┬───────┘ └──────┬──────┘ └──────┬───────┘                      │
│         │                │               │                               │
│         ▼                ▼               ▼                                │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │                    Claude Layer                                   │    │
│  │                                                                   │    │
│  │  CLAUDE.md    .claude/settings.json    .claude/rules/*           │    │
│  │  .claude/agents/*    .claude/skills/*    hooks/*                  │    │
│  │  .mcp.json (profiles)                                            │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │                    Foundry Storage                                │    │
│  │                                                                   │    │
│  │  PostgreSQL: runs, run_events, run_artifacts, run_reviews,       │    │
│  │              worktrees, batch_jobs, batch_items, eval_runs,      │    │
│  │              eval_results, verification_results, mcp_profiles    │    │
│  │  Redis: task queue, run status pub/sub                           │    │
│  │  Object storage: artifacts (plans, diffs, patches, logs)         │    │
│  └──────────────────────────────────────────────────────────────────┘    │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │
                                 │  git worktrees / PRs / artifacts
                                 │  JSON schemas / OpenAPI contracts
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                            unicorn-app                                   │
│                                                                          │
│  Next.js (TS)  ──▶  Go API  ──▶  PostgreSQL + pgvector                  │
│                       │                                                  │
│                       ▼                                                  │
│                  Go Workers  ──▶  Redis queues  ──▶  Object storage     │
│                                                                          │
│  Domains: companies, events, evidence, state, scoring, search           │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Repository Structure

```
unicorn-foundry/
├── CLAUDE.md                          # repo-wide non-negotiable guidance
├── .claude/
│   ├── settings.json                  # permissions, hooks, additional dirs
│   ├── rules/
│   │   ├── repo-safety.md             # never touch secrets, migrations guard
│   │   ├── api-contracts.md           # OpenAPI-first, schema validation
│   │   ├── testing.md                 # test requirements per change type
│   │   ├── pr-standards.md            # PR title, body, labels, artifact links
│   │   └── migrations.md              # migration-specific review escalation
│   ├── agents/
│   │   ├── planner.md                 # file-level implementation planning
│   │   ├── repo-explorer.md           # read-only reconnaissance
│   │   ├── backend-implementer.md     # Go implementation specialist
│   │   ├── frontend-implementer.md    # TS/Next.js specialist
│   │   ├── reviewer.md                # independent diff reviewer
│   │   ├── migration-guard.md         # high-scrutiny infra/auth/migration review
│   │   └── extractor.md              # signal-to-event extraction specialist
│   └── skills/
│       ├── spec-to-plan/
│       │   └── SKILL.md
│       ├── endpoint-generator/
│       │   └── SKILL.md
│       ├── safe-refactor/
│       │   └── SKILL.md
│       ├── review-diff/
│       │   └── SKILL.md
│       ├── issue-to-pr/
│       │   └── SKILL.md
│       ├── extract-signals/
│       │   └── SKILL.md
│       └── run-eval/
│           └── SKILL.md
├── .mcp.json                          # MCP server connections + profiles
├── app/
│   ├── __init__.py
│   ├── main.py                        # FastAPI app entry
│   ├── config.py                      # env, model routing, MCP profiles
│   ├── deps.py                        # dependency injection
│   └── routes/
│       ├── runs.py
│       ├── reviews.py
│       ├── specs.py
│       ├── patches.py
│       ├── batches.py
│       ├── evals.py
│       ├── worktrees.py
│       └── health.py
├── foundry/
│   ├── __init__.py
│   ├── contracts/
│   │   ├── task_types.py              # Pydantic models for every task type
│   │   ├── run_models.py             # run state, events, artifacts
│   │   ├── review_models.py          # review verdicts, issues
│   │   ├── extraction_models.py      # event/evidence schemas
│   │   ├── eval_models.py            # eval definitions, results
│   │   └── shared.py                 # common enums, base models
│   ├── db/
│   │   ├── engine.py
│   │   ├── models.py                 # SQLAlchemy ORM models
│   │   ├── migrations/               # Alembic
│   │   └── queries/
│   │       ├── runs.py
│   │       ├── artifacts.py
│   │       ├── batches.py
│   │       └── evals.py
│   ├── orchestration/
│   │   ├── run_engine.py             # core run lifecycle state machine
│   │   ├── agent_runner.py           # Agent SDK wrapper
│   │   ├── model_router.py           # opus/sonnet/haiku routing
│   │   └── prompt_templates.py       # system prompts per agent/task
│   ├── git/
│   │   ├── worktree.py               # create, list, cleanup worktrees
│   │   ├── branch.py                 # branch naming, management
│   │   └── pr.py                     # PR creation via GitHub API
│   ├── providers/
│   │   ├── claude_agent.py           # Agent SDK integration
│   │   ├── claude_messages.py        # raw Messages API integration
│   │   ├── claude_batch.py           # Message Batches API integration
│   │   └── github.py                 # GitHub REST/GraphQL client
│   ├── tasks/
│   │   ├── endpoint_build.py
│   │   ├── refactor.py
│   │   ├── migration_plan.py
│   │   ├── bug_fix.py
│   │   ├── feature_slice.py
│   │   ├── extraction_batch.py
│   │   ├── eval_run.py
│   │   └── review_diff.py
│   ├── verification/
│   │   ├── go_verify.py              # go build, go test, go vet, lint
│   │   ├── ts_verify.py              # tsc, eslint, next build
│   │   ├── schema_verify.py          # OpenAPI + JSON Schema validation
│   │   └── runner.py                 # dispatch verification by file type
│   └── storage/
│       ├── artifact_store.py         # write/read artifacts to object storage
│       └── log_store.py              # structured run event logging
├── workers/
│   ├── run_worker.py                 # picks tasks from Redis, runs them
│   ├── batch_worker.py               # manages batch API polling
│   └── cleanup_worker.py             # periodic worktree/artifact cleanup
├── hooks/
│   ├── pre_tool_use/
│   │   ├── block_secrets.sh          # deny read/write to secret paths
│   │   ├── block_protected_paths.sh  # guard migrations, auth, infra
│   │   └── require_plan.sh           # block implementation without plan artifact
│   └── post_tool_use/
│       ├── verify_after_edit.sh      # run targeted verification after file edits
│       └── log_tool_call.sh          # append to run event log
├── artifacts/                         # local artifact staging (ephemeral)
├── evals/
│   ├── datasets/
│   │   ├── extraction_accuracy.jsonl
│   │   ├── evidence_strength.jsonl
│   │   └── state_inference.jsonl
│   ├── scorers/
│   │   ├── extraction_scorer.py
│   │   ├── evidence_scorer.py
│   │   └── state_scorer.py
│   └── runner.py
├── canon/
│   ├── schemas/                       # JSON Schemas shared with unicorn-app
│   │   ├── event.schema.json
│   │   ├── evidence.schema.json
│   │   ├── company_state.schema.json
│   │   ├── scorecard.schema.json
│   │   └── extraction_result.schema.json
│   └── docs/
│       ├── event_taxonomy.md
│       ├── evidence_taxonomy.md
│       ├── state_model.md
│       └── scoring_methodology.md
├── scripts/
│   ├── seed_db.py
│   ├── run_task.py                    # CLI for ad-hoc task submission
│   └── export_artifacts.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## 5. Task Types

Every Foundry operation is a typed task. Each type defines its required inputs, allowed tools, MCP profile, verification steps, and output schema.

| Task Type | Lane | Model | MCP Profile | Outputs |
|---|---|---|---|---|
| `endpoint_build` | Agent SDK | Sonnet 4.6 | `github_postgres_readonly` | plan + diff + PR |
| `feature_slice` | Agent SDK | Sonnet 4.6 | `github_postgres_readonly` | plan + diff + PR |
| `bug_fix` | Agent SDK | Sonnet 4.6 | `github_only` | plan + diff + PR |
| `refactor` | Agent SDK | Sonnet 4.6 | `github_only` | plan + diff + PR |
| `migration_plan` | Agent SDK | Opus 4.6 | `github_postgres_readonly` | plan artifact only |
| `architecture_review` | Agent SDK | Opus 4.6 | `github_postgres_readonly` | review artifact |
| `review_diff` | Agent SDK | Opus 4.6 | `github_only` | review verdict |
| `extraction_batch` | Batch API | Haiku 4.5 / Sonnet 4.6 | `none` | structured JSON |
| `evidence_classification` | Batch API | Haiku 4.5 | `none` | structured JSON |
| `eval_run` | Batch API | Sonnet 4.6 | `none` | eval results |
| `canon_update` | Agent SDK | Opus 4.6 | `github_only` | plan + diff + PR |

### Task Contract (Pydantic)

```python
class TaskRequest(BaseModel):
    task_type: TaskType                    # enum of above
    repo: Literal["unicorn-app", "unicorn-foundry"]
    base_branch: str = "main"
    title: str
    prompt: str
    target_paths: list[str] = []          # scope hints
    allowed_tools: list[str] = ["Read", "Edit", "Write", "Bash", "Grep", "Glob"]
    mcp_profile: MCPProfile = MCPProfile.NONE
    model_override: str | None = None     # override default routing
    verify: bool = True
    open_pr: bool = True
    priority: int = 0
    metadata: dict = {}
```

---

## 6. Run Lifecycle — State Machine

```
                              ┌─────────┐
                              │ queued  │
                              └────┬────┘
                                   │
                              ┌────▼────┐
                              │creating │  ← worktree created
                              │worktree │
                              └────┬────┘
                                   │
                              ┌────▼────┐
                     ┌────────│planning │
                     │        └────┬────┘
                     │             │ structured plan produced
                     │        ┌────▼─────────┐
                     │        │implementing  │
                     │        └────┬─────────┘
                     │             │
                     │        ┌────▼────┐
                     │        │verifying│
                     │        └────┬────┘
                     │             │
                     │        ┌────┤
                     │        │    │
             plan_failed      │    ▼
             (artifact +  ┌───▼──────────┐
              notes)      │verification  │──── verification_failed
                          │passed        │     (artifact + notes)
                          └───┬──────────┘
                              │
                         ┌────▼─────┐
                         │reviewing │
                         └────┬─────┘
                              │
                    ┌─────────┤
                    │         │
              review_failed   │
              (artifact +     ▼
               notes)    ┌────────┐
                         │pr_open │
                         └────┬───┘
                              │
                         ┌────▼─────┐
                         │completed │
                         └──────────┘

        At any point:
        ─── cancelled (via API)
        ─── errored (unhandled failure)
```

### Run State Enum

```python
class RunState(str, Enum):
    QUEUED = "queued"
    CREATING_WORKTREE = "creating_worktree"
    PLANNING = "planning"
    IMPLEMENTING = "implementing"
    VERIFYING = "verifying"
    VERIFICATION_PASSED = "verification_passed"
    REVIEWING = "reviewing"
    PR_OPENED = "pr_opened"
    COMPLETED = "completed"
    PLAN_FAILED = "plan_failed"
    VERIFICATION_FAILED = "verification_failed"
    REVIEW_FAILED = "review_failed"
    CANCELLED = "cancelled"
    ERRORED = "errored"
```

### Run Event Schema

Every state transition emits a `RunEvent`:

```python
class RunEvent(BaseModel):
    run_id: UUID
    timestamp: datetime
    state: RunState
    message: str
    artifact_ids: list[UUID] = []
    metadata: dict = {}
    duration_ms: int | None = None
    model_used: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
```

---

## 7. Subagent Definitions

Each subagent has a focused role, its own system prompt, limited tool access, and an independent context window.

### 7.1 Planner

**Purpose:** Given a task spec + repo state, produce a file-level implementation plan as structured JSON.

**Tools:** `Read`, `Grep`, `Glob` (read-only)  
**Model:** Sonnet 4.6 (Opus 4.6 for architecture/migration tasks)  
**Output:** `PlanArtifact` — list of files to create/modify/delete with rationale for each.

```python
class PlanStep(BaseModel):
    file_path: str
    action: Literal["create", "modify", "delete"]
    rationale: str
    dependencies: list[str] = []

class PlanArtifact(BaseModel):
    task_id: UUID
    steps: list[PlanStep]
    risks: list[str]
    open_questions: list[str]
    estimated_complexity: Literal["trivial", "small", "medium", "large", "critical"]
```

### 7.2 Repo Explorer

**Purpose:** Read-only reconnaissance. Discovers patterns, conventions, module structure, test conventions.  
**Tools:** `Read`, `Grep`, `Glob`  
**Model:** Haiku 4.5 (fast, cheap)  
**Output:** Structured JSON summary of discovered patterns.

### 7.3 Backend Implementer

**Purpose:** Go implementation per plan steps.  
**Tools:** `Read`, `Edit`, `Write`, `Bash`, `Grep`, `Glob`  
**Model:** Sonnet 4.6  
**Constraints:** Can only write to paths listed in plan. Bash restricted to `go build`, `go test`, `go vet`, `golangci-lint`.

### 7.4 Frontend Implementer

**Purpose:** TypeScript/Next.js implementation per plan steps.  
**Tools:** `Read`, `Edit`, `Write`, `Bash`, `Grep`, `Glob`  
**Model:** Sonnet 4.6  
**Constraints:** Can only write to paths listed in plan. Bash restricted to `tsc`, `eslint`, `next build`, `npm test`.

### 7.5 Reviewer

**Purpose:** Independent review of a diff. Has no access to the plan — judges the diff on its own merits.  
**Tools:** `Read`, `Grep`, `Glob` (read-only)  
**Model:** Opus 4.6  
**Output:**

```python
class ReviewVerdict(BaseModel):
    verdict: Literal["approve", "request_changes", "reject"]
    issues: list[ReviewIssue]
    summary: str

class ReviewIssue(BaseModel):
    severity: Literal["critical", "major", "minor", "nit"]
    file_path: str
    line_range: str | None
    description: str
    suggestion: str | None
```

### 7.6 Migration Guard

**Purpose:** High-scrutiny reviewer for anything touching migrations, auth, infra, config, or secrets.  
**Tools:** `Read`, `Grep`, `Glob`  
**Model:** Opus 4.6  
**Trigger:** Automatically invoked if any changed file matches `migrations/`, `auth/`, `infra/`, `*.env*`, `docker-compose*`, `Dockerfile*`.

### 7.7 Extractor

**Purpose:** Transform raw source material into structured event/evidence JSON per the canon schemas.  
**Tools:** None (pure text-in, JSON-out via Messages API)  
**Model:** Sonnet 4.6 for complex sources, Haiku 4.5 for simple classification  
**Output:** Validated against `event.schema.json` and `evidence.schema.json`.

---

## 8. Skills

### 8.1 spec-to-plan

```markdown
# SKILL.md — spec-to-plan

Trigger: User provides a feature spec or describes work to be done.

Workflow:
1. Receive spec as natural language or structured input.
2. Call repo-explorer subagent to understand current module layout.
3. Identify all files that need to change.
4. Produce a PlanArtifact with ordered steps, dependencies, risks.
5. Validate plan against existing OpenAPI contracts.
6. Return structured JSON plan.

Output schema: PlanArtifact
```

### 8.2 endpoint-generator

```markdown
# SKILL.md — endpoint-generator

Trigger: "Build endpoint", "Add API route", or plan step targeting services/api/.

Workflow:
1. Read existing router registration pattern.
2. Read existing handler patterns in the target domain.
3. Generate handler + request/response types + route registration.
4. Generate corresponding OpenAPI spec additions.
5. Generate test file matching existing test conventions.
6. Run go build + go test.

Verification: Compilation passes, tests pass, OpenAPI validates.
```

### 8.3 safe-refactor

```markdown
# SKILL.md — safe-refactor

Trigger: "Refactor", "Clean up", "Restructure".

Workflow:
1. Plan: identify all usages of target symbol/module.
2. Execute refactor in smallest possible atomic steps.
3. Run full test suite after each step.
4. If any step breaks tests, revert that step and report.
5. Produce diff artifact.

Constraint: Never combine behavioral changes with structural changes.
```

### 8.4 review-diff

```markdown
# SKILL.md — review-diff

Trigger: PR opened, or explicit review request.

Workflow:
1. Read the full diff.
2. Read surrounding context for each changed file.
3. Check contract compliance (OpenAPI, JSON Schema).
4. Check test coverage for new code paths.
5. Check for security anti-patterns.
6. Produce ReviewVerdict.
```

### 8.5 extract-signals

```markdown
# SKILL.md — extract-signals

Trigger: Raw source material needs normalization.

Workflow:
1. Receive raw source text + source metadata.
2. Classify source type (funding, launch, hire, partnership, etc.).
3. Extract structured events per event.schema.json.
4. Attach evidence objects per evidence.schema.json.
5. Assign confidence scores.
6. Return validated JSON array.

Model: Sonnet 4.6 for ambiguous sources, Haiku 4.5 for clear-cut ones.
```

### 8.6 run-eval

```markdown
# SKILL.md — run-eval

Trigger: Eval dataset + scorer specified.

Workflow:
1. Load eval dataset (JSONL).
2. For each item, call the appropriate model with the extraction/scoring prompt.
3. Collect outputs.
4. Run scorer against expected outputs.
5. Compute aggregate metrics (precision, recall, F1, accuracy).
6. Store results as eval artifact.
```

---

## 9. Hooks

### 9.1 PreToolUse Hooks

**block_secrets.sh**
```bash
#!/bin/bash
# Denies Read/Edit/Write to any path matching secret patterns.
# Registered for: Read, Edit, Write
# Action on match: DENY

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name')
PATH_ARG=$(echo "$INPUT" | jq -r '.tool_input.path // .tool_input.file_path // empty')

BLOCKED_PATTERNS=(
    "*.env"
    "*.env.*"
    "*secrets*"
    "*credentials*"
    "*.pem"
    "*.key"
    "*service-account*"
)

for pattern in "${BLOCKED_PATTERNS[@]}"; do
    if [[ "$PATH_ARG" == $pattern ]]; then
        echo '{"decision": "deny", "reason": "Access to secret/credential files is blocked."}'
        exit 0
    fi
done

echo '{"decision": "allow"}'
```

**block_protected_paths.sh**
```bash
#!/bin/bash
# Blocks casual writes to migrations, auth, infra without explicit task authorization.
# Registered for: Edit, Write
# Checks RUN_TASK_TYPE env var; only migration_plan and canon_update tasks can touch these.

INPUT=$(cat)
PATH_ARG=$(echo "$INPUT" | jq -r '.tool_input.path // .tool_input.file_path // empty')

PROTECTED_DIRS=("migrations/" "infra/" "auth/" "docker-compose" "Dockerfile")

for dir in "${PROTECTED_DIRS[@]}"; do
    if [[ "$PATH_ARG" == *"$dir"* ]]; then
        if [[ "$RUN_TASK_TYPE" != "migration_plan" && "$RUN_TASK_TYPE" != "canon_update" ]]; then
            echo '{"decision": "deny", "reason": "Protected path. Requires migration_plan or canon_update task type."}'
            exit 0
        fi
    fi
done

echo '{"decision": "allow"}'
```

**require_plan.sh**
```bash
#!/bin/bash
# Blocks Edit/Write if no plan artifact exists for the current run.
# Registered for: Edit, Write (only during implementing phase)

INPUT=$(cat)

if [[ "$RUN_STATE" == "implementing" && ! -f "$ARTIFACT_DIR/plan.json" ]]; then
    echo '{"decision": "deny", "reason": "No plan artifact found. Planning phase must complete first."}'
    exit 0
fi

echo '{"decision": "allow"}'
```

### 9.2 PostToolUse Hooks

**verify_after_edit.sh**
```bash
#!/bin/bash
# After any Edit/Write to a .go file, run go vet on the package.
# After any Edit/Write to a .ts/.tsx file, run tsc --noEmit.

INPUT=$(cat)
PATH_ARG=$(echo "$INPUT" | jq -r '.tool_input.path // .tool_input.file_path // empty')

if [[ "$PATH_ARG" == *.go ]]; then
    PKG_DIR=$(dirname "$PATH_ARG")
    cd "$WORKTREE_PATH" && go vet "./$PKG_DIR/..." 2>&1
fi

if [[ "$PATH_ARG" == *.ts || "$PATH_ARG" == *.tsx ]]; then
    cd "$WORKTREE_PATH" && npx tsc --noEmit 2>&1
fi
```

**log_tool_call.sh**
```bash
#!/bin/bash
# Appends every tool call to the run event log for observability.

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name')
PATH_ARG=$(echo "$INPUT" | jq -r '.tool_input.path // .tool_input.file_path // "n/a"')
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

echo "{\"ts\":\"$TIMESTAMP\",\"tool\":\"$TOOL\",\"path\":\"$PATH_ARG\",\"run_id\":\"$RUN_ID\"}" >> "$ARTIFACT_DIR/tool_log.jsonl"
```

### Hook Registration (.claude/settings.json excerpt)

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Read|Edit|Write",
        "command": "hooks/pre_tool_use/block_secrets.sh"
      },
      {
        "matcher": "Edit|Write",
        "command": "hooks/pre_tool_use/block_protected_paths.sh"
      },
      {
        "matcher": "Edit|Write",
        "command": "hooks/pre_tool_use/require_plan.sh"
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "command": "hooks/post_tool_use/verify_after_edit.sh"
      },
      {
        "matcher": "*",
        "command": "hooks/post_tool_use/log_tool_call.sh"
      }
    ]
  }
}
```

---

## 10. MCP Profiles

Defined in `.mcp.json` with profile selectors. Each run gets only the tools it needs.

| Profile | Servers | Use Case |
|---|---|---|
| `none` | — | Batch extraction, evals |
| `github_only` | GitHub | Bug fixes, refactors, reviews |
| `github_postgres_readonly` | GitHub, Postgres (read-only) | Endpoint builds, feature slices, architecture review |
| `research_full` | GitHub, Postgres (RO), Browser | Architecture planning, canon research |
| `app_build_minimal` | GitHub | Simple code changes |

```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": { "GITHUB_TOKEN": "${GITHUB_TOKEN}" }
    },
    "postgres_readonly": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres"],
      "env": { "DATABASE_URL": "${FOUNDRY_DB_READONLY_URL}" }
    }
  }
}
```

Profile assignment happens in `foundry/orchestration/run_engine.py` based on `task_request.mcp_profile`.

---

## 11. Model Routing

```python
MODEL_ROUTING: dict[str, dict[str, str]] = {
    # Task type → agent role → model
    "endpoint_build": {
        "planner": "claude-sonnet-4-6",
        "implementer": "claude-sonnet-4-6",
        "reviewer": "claude-opus-4-6",
    },
    "migration_plan": {
        "planner": "claude-opus-4-6",
        "reviewer": "claude-opus-4-6",
        "migration_guard": "claude-opus-4-6",
    },
    "extraction_batch": {
        "extractor": "claude-sonnet-4-6",       # complex sources
        "classifier": "claude-haiku-4-5",        # simple tagging
    },
    "eval_run": {
        "evaluator": "claude-sonnet-4-6",
    },
    "review_diff": {
        "reviewer": "claude-opus-4-6",
    },
    "architecture_review": {
        "planner": "claude-opus-4-6",
        "reviewer": "claude-opus-4-6",
    },
    # defaults
    "_default": {
        "planner": "claude-sonnet-4-6",
        "implementer": "claude-sonnet-4-6",
        "reviewer": "claude-opus-4-6",
        "explorer": "claude-haiku-4-5",
    },
}
```

**Routing principle:** Opus for judgment-heavy work (review, architecture, red-teaming). Sonnet for implementation and structured extraction. Haiku for classification, tagging, and reconnaissance.

---

## 12. Data Flow: Build Loop

```
Human writes spec / files issue
         │
         ▼
POST /v1/runs  { task_type: "endpoint_build", ... }
         │
         ▼
run_worker picks up from Redis queue
         │
         ▼
worktree_manager.create(repo="unicorn-app", branch="foundry/endpoint-timeline")
         │
         ▼
planner subagent → reads repo → produces PlanArtifact (stored)
         │
         ▼
backend_implementer subagent → writes code per plan (worktree only)
         │
         ▼
verification.runner → go build + go test + go vet + OpenAPI validate
         │
    ┌────┤
    │ FAIL: store verification_failed artifact, transition to verification_failed
    │
    ▼ PASS
reviewer subagent → reads diff (no plan access) → produces ReviewVerdict
         │
    ┌────┤
    │ REJECT/REQUEST_CHANGES: store review artifact, transition to review_failed
    │
    ▼ APPROVE
migration_guard subagent (if triggered by path match)
         │
         ▼
git.pr.create → opens PR on GitHub with artifact links in body
         │
         ▼
transition to completed, all artifacts stored
```

## 13. Data Flow: Extraction Loop

```
Raw sources (URLs, text dumps, API responses)
         │
         ▼
POST /v1/batches/extract  { sources: [...], schema: "event", model: "sonnet" }
         │
         ▼
batch_worker creates Message Batch via Anthropic API
  - system prompt: canon/docs/event_taxonomy.md + canon/schemas/event.schema.json
  - each message: one source document
  - structured output mode: JSON matching event.schema.json
  - prompt caching: system prompt cached across batch
         │
         ▼
poll until batch complete
         │
         ▼
for each result:
  - validate against JSON Schema
  - store in batch_items table
  - if valid: write to artifacts/extraction/{batch_id}/{item_id}.json
  - if invalid: flag for human review
         │
         ▼
POST /internal/ingest/source on unicorn-app (for each valid extraction)
         │
         ▼
unicorn-app worker: normalize → events table → evidence table → state recompute → read model refresh
```

## 14. Data Flow: Eval Loop

```
POST /v1/evals/run  { dataset: "extraction_accuracy", scorer: "extraction_scorer", model: "sonnet" }
         │
         ▼
eval_runner loads dataset from evals/datasets/extraction_accuracy.jsonl
         │
         ▼
for each item:
  - send source text to model with extraction prompt
  - collect structured output
         │
         ▼
scorer compares output to expected (per evals/scorers/extraction_scorer.py)
         │
         ▼
aggregate metrics: precision, recall, F1, per-field accuracy
         │
         ▼
store eval_results artifact
         │
         ▼
log to eval_runs + eval_results tables
```

---

## 15. Foundry ↔ App Interaction

The two systems interact through **three channels only**:

### 15.1 Git (primary)

Foundry creates PRs against `unicorn-app`. Human reviews and merges. This is the only path for code changes. Foundry never writes directly to `unicorn-app`'s database or deploys anything.

### 15.2 Internal API (data pipeline)

Foundry calls `unicorn-app`'s internal endpoints to push extracted/normalized data:

```
POST /internal/ingest/source       — push new source + extracted events
POST /internal/recompute/company/{id}  — trigger state recompute
POST /internal/reindex/search      — trigger search index rebuild
```

These endpoints are authenticated with a service token and rate-limited.

### 15.3 Shared Contracts (schemas)

Both repos consume the same JSON Schemas from `canon/schemas/`. In practice, Foundry is the source of truth for schemas. When schemas change:

1. Foundry updates `canon/schemas/*.schema.json`
2. Foundry opens a PR against `unicorn-app` with the updated schemas + any generated code changes
3. Human reviews and merges

---

## 16. Deterministic vs. Agentic Boundary

| Deterministic (never LLM) | Agentic (Claude) |
|---|---|
| Worktree creation/cleanup | Planning |
| Git branch naming | Implementation |
| PR template population | Review judgment |
| JSON Schema validation | Signal extraction |
| go build / go test / tsc | Evidence classification |
| OpenAPI spec validation | Eval scoring |
| Run state machine transitions | Ambiguous source interpretation |
| Artifact storage | Architecture reasoning |
| Queue management | Prompt generation for batch jobs |
| Model routing dispatch | — |
| Hook execution | — |
| Batch API polling | — |
| Metric aggregation | — |

**Rule:** If it can be a `if/else` or a schema check, it must not be an LLM call.

---

## 17. Storage: Artifact Types

Every run produces typed artifacts stored in object storage with metadata in Postgres.

| Artifact Type | Format | Produced By |
|---|---|---|
| `plan` | JSON (PlanArtifact) | planner |
| `diff` | unified diff | implementer |
| `patch` | git format-patch | implementer |
| `verification_result` | JSON | verification runner |
| `review` | JSON (ReviewVerdict) | reviewer |
| `tool_log` | JSONL | post_tool_use hook |
| `extraction_result` | JSON array | extractor |
| `eval_result` | JSON (metrics + per-item scores) | eval runner |
| `pr_metadata` | JSON (url, number, branch) | PR creator |
| `error_log` | text | run engine (on failure) |

Artifact path convention in object storage:
```
foundry/runs/{run_id}/{artifact_type}.json
foundry/batches/{batch_id}/items/{item_id}.json
foundry/evals/{eval_id}/results.json
```

---

## 18. Foundry Database Schema

```sql
-- Runs
CREATE TABLE runs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_type     TEXT NOT NULL,
    repo          TEXT NOT NULL,
    base_branch   TEXT NOT NULL DEFAULT 'main',
    title         TEXT NOT NULL,
    prompt        TEXT NOT NULL,
    state         TEXT NOT NULL DEFAULT 'queued',
    mcp_profile   TEXT NOT NULL DEFAULT 'none',
    worktree_path TEXT,
    branch_name   TEXT,
    pr_url        TEXT,
    error_message TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at  TIMESTAMPTZ,
    metadata      JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE run_events (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id       UUID NOT NULL REFERENCES runs(id),
    state        TEXT NOT NULL,
    message      TEXT NOT NULL,
    model_used   TEXT,
    tokens_in    INT,
    tokens_out   INT,
    duration_ms  INT,
    metadata     JSONB NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_run_events_run_id ON run_events(run_id);

CREATE TABLE run_artifacts (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id        UUID NOT NULL REFERENCES runs(id),
    artifact_type TEXT NOT NULL,
    storage_path  TEXT NOT NULL,
    size_bytes    BIGINT,
    checksum      TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_run_artifacts_run_id ON run_artifacts(run_id);

-- Worktrees
CREATE TABLE worktrees (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id       UUID REFERENCES runs(id),
    repo         TEXT NOT NULL,
    branch_name  TEXT NOT NULL,
    path         TEXT NOT NULL,
    state        TEXT NOT NULL DEFAULT 'active',  -- active, cleaned
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    cleaned_at   TIMESTAMPTZ
);

-- Batches
CREATE TABLE batch_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_type      TEXT NOT NULL,
    anthropic_batch_id TEXT,
    state           TEXT NOT NULL DEFAULT 'pending',
    total_items     INT NOT NULL DEFAULT 0,
    completed_items INT NOT NULL DEFAULT 0,
    failed_items    INT NOT NULL DEFAULT 0,
    model           TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    metadata        JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE batch_items (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id     UUID NOT NULL REFERENCES batch_jobs(id),
    input_hash   TEXT NOT NULL,
    state        TEXT NOT NULL DEFAULT 'pending',
    result_path  TEXT,
    is_valid     BOOLEAN,
    error        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_batch_items_batch_id ON batch_items(batch_id);

-- Evals
CREATE TABLE eval_runs (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset      TEXT NOT NULL,
    scorer       TEXT NOT NULL,
    model        TEXT NOT NULL,
    state        TEXT NOT NULL DEFAULT 'running',
    metrics      JSONB,
    result_path  TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

-- Verification
CREATE TABLE verification_results (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id       UUID NOT NULL REFERENCES runs(id),
    check_type   TEXT NOT NULL,  -- go_build, go_test, tsc, openapi_validate, etc.
    passed       BOOLEAN NOT NULL,
    output       TEXT,
    duration_ms  INT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_verification_run_id ON verification_results(run_id);
```

---

## 19. CLAUDE.md

```markdown
# Unicorn Foundry — Project Guidance

## Identity
You are operating inside unicorn-foundry, the internal Claude orchestration
system for Unicorn Protocol. You build, review, extract, and evaluate.

## Non-Negotiable Rules
1. Always plan before implementing non-trivial changes.
2. All code edits happen in worktrees, never on main.
3. Run verification (build + test + lint) before any PR.
4. Every run must produce stored artifacts.
5. Never read or write secret/credential files.
6. Never modify migrations, auth, or infra without explicit task authorization.
7. Reviewer subagent must not see the plan — it judges the diff independently.
8. Extraction outputs must validate against canon JSON Schemas.

## Repo Layout
- app/ — FastAPI control plane
- foundry/ — orchestration core
- workers/ — background task runners
- hooks/ — deterministic enforcement scripts
- evals/ — datasets and scorers
- canon/ — shared schemas and domain docs
- artifacts/ — ephemeral local staging

## Canon
The source of truth for domain models is in canon/. Always read the relevant
canon doc before extraction or schema work:
- canon/docs/event_taxonomy.md
- canon/docs/evidence_taxonomy.md
- canon/docs/state_model.md
- canon/docs/scoring_methodology.md

## Model Usage
- Opus 4.6: architecture, planning, review, migration guard
- Sonnet 4.6: implementation, extraction, evals
- Haiku 4.5: classification, tagging, reconnaissance

## Structured Output
All plans, reviews, extractions, and evals must return validated JSON.
Never return prose where structured output is expected.
```

---

## 20. Implementation Phases

### Phase 0 — Skeleton (Week 1)

- [ ] Initialize `unicorn-foundry` repo with exact directory structure above
- [ ] Write `CLAUDE.md`, `.claude/settings.json`, all rule files
- [ ] Write Pydantic models in `foundry/contracts/`
- [ ] Stand up FastAPI with health endpoint
- [ ] Postgres schema + Alembic migrations for all tables
- [ ] Docker Compose: Postgres, Redis, FastAPI app

### Phase 1 — Run Engine (Week 2–3)

- [ ] Implement `run_engine.py` state machine
- [ ] Implement `worktree.py` (create, cleanup)
- [ ] Implement `agent_runner.py` wrapping Agent SDK
- [ ] Implement `model_router.py`
- [ ] Write planner + backend-implementer subagent definitions
- [ ] Implement `run_worker.py` consuming from Redis
- [ ] Implement all hooks
- [ ] End-to-end: submit task → plan → implement → verify → review → PR

### Phase 2 — Verification + Review (Week 3–4)

- [ ] Implement `go_verify.py`, `ts_verify.py`, `schema_verify.py`
- [ ] Implement reviewer subagent with blind diff review
- [ ] Implement migration_guard auto-trigger
- [ ] Implement `artifact_store.py` writing to object storage
- [ ] Implement full run event logging

### Phase 3 — Extraction Pipeline (Week 4–5)

- [ ] Write canon schemas: `event.schema.json`, `evidence.schema.json`
- [ ] Write canon docs: event taxonomy, evidence taxonomy
- [ ] Implement `claude_batch.py` wrapping Message Batches API
- [ ] Implement `batch_worker.py` with polling
- [ ] Implement extract-signals skill
- [ ] Implement extractor subagent
- [ ] End-to-end: raw source → batch extraction → validated JSON → unicorn-app ingest

### Phase 4 — Evals (Week 5–6)

- [ ] Create initial eval datasets (50–100 items each)
- [ ] Implement scorers
- [ ] Implement `eval_runner.py`
- [ ] Implement `/v1/evals/run` route
- [ ] Baseline extraction accuracy + evidence classification accuracy

### Phase 5 — Polish + Ops (Week 6–7)

- [ ] Cleanup worker for stale worktrees
- [ ] Retry logic for failed runs
- [ ] Cost tracking per run (tokens × model pricing)
- [ ] Simple admin dashboard or CLI for run monitoring
- [ ] Integration tests for full run lifecycle
- [ ] Documentation: README, API docs, runbook

---

## 21. Tradeoffs and Failure Modes

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Agent produces invalid code that passes verification | Medium | High | Reviewer subagent as independent check; migration guard for critical paths |
| Worktree accumulation fills disk | High | Medium | Cleanup worker on schedule + per-run cleanup on completion |
| Batch extraction hallucinates events | Medium | High | JSON Schema validation catches structural errors; eval pipeline catches semantic drift |
| Model cost blows up on retry loops | Medium | Medium | Max retries per run (3); cost cap per run; alert on anomalous token usage |
| Foundry DB diverges from app DB schema understanding | Low | High | Canon schemas as single source; any schema change triggers both repos |
| Hook scripts have bugs that block all edits | Low | High | Hook dry-run mode; ability to disable hooks per run for debugging |
| PR flood overwhelms human reviewers | Medium | Low | Priority queue; daily PR budget; batch similar changes |
| Prompt injection via source material in extraction | Medium | High | Extraction prompts use strict system instructions; structured output mode constrains output shape; never pass raw source as system prompt |
| Agent SDK breaking changes | Low | Medium | Pin SDK version; integration tests catch regressions |
| State machine gets stuck in intermediate state | Low | Medium | Timeout per state (configurable); auto-transition to errored after timeout |

---

## 22. What Must Not Be Built

- **No chat interface for Foundry.** It is a task engine, not a conversation.
- **No direct database writes from Foundry to unicorn-app's Postgres.** All data flows through the internal API or git PRs.
- **No live Claude calls in unicorn-app's user request path.** The app serves precomputed truth.
- **No monorepo.** The repos stay separate.
- **No agent teams in v1.** Subagents are sufficient. Teams introduce coordination complexity that is not yet justified.
