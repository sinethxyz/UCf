# Continuity

**An experiment in intelligence through time.**

A useful model response is not the same thing as a coherent sequence of actions.

A system can produce a good plan and lose the reason for it. It can make a change without establishing what actually changed. It can finish a task and leave the next operation with no reliable account of the result.

Continuity explores the infrastructure around that problem: explicit state, controlled action, observation, verification, and a record that survives the interaction.

> **The model is a participant in the loop, not the loop itself.**

This is an experimental software runtime, originally developed as **Unicorn Foundry / UCF**. “Intelligence through time” names the question being investigated, not a claim that the repository has solved it.

[Architecture](#architecture) · [Evidence and status](#evidence-and-status) · [Run the tests](#run-the-tests) · [Origin](#origin) · [Retrospective](RETROSPECTIVE.md)

## The problem

A model call starts with context and produces an output. An operating system around that call has additional responsibilities: representing its environment, tracking what is known, deciding which actions are permitted, checking consequences, and carrying useful state forward.

Continuity treats these as explicit engineering concerns rather than assuming they disappear when the model improves.

The working question is:

> **What must exist around an intelligent model for it to remain coherent while the environment it operates in changes?**

## The loop

```text
environment
    ↓ observe
state(t) + evidence
    ↓ reason / plan
proposed action
    ↓ controlled execution
changed environment
    ↓ observe and verify
outcome + observed state(t+1)
    ↺ next operation
```

The unit of work is a **state transition**, not a chat response.

State is a representation derived from observations, not guaranteed ground truth. A verification decision is only as strong as the checks and evidence behind it. Preserving a snapshot also does not, by itself, prove that it still matches the environment later.

A planner may use a language model, deterministic logic, or another reasoning mechanism. The generic loop is expressed through interfaces; the concrete provider and environment implementations remain limited and experimental.

## Architecture

The repository contains three related layers, not a completed rewrite.

| Layer | Responsibility | Current implementation |
| --- | --- | --- |
| Transition core | Coordinate observation, planning, action, verification, and outcome recording | `TransitionEngine` and capability interfaces |
| Foundry adapter | Connect the general interfaces to the original software-engineering environment | Git worktrees, `AgentRunner`, code verification, review, artifact storage |
| Historical runtime | Preserve the existing API, database, event, and pull-request lifecycle | `RunEngine`, FastAPI, PostgreSQL, Redis, workers |

The historical runtime does not yet delegate its complete lifecycle to the transition core. Likewise, accepting an outcome is not the same as publishing, merging, or deploying a change.

The public name is **Continuity**. Python imports still use `foundry`, the distribution remains `unicorn-foundry`, and historical configuration names remain unchanged. This introduction does not rename packages or break existing imports.

## Evidence and status

The following is a dated record, not a claim that every planned capability is available.

**Merged baseline:** commit `6cc52e5e8dd22bccf6d00b7e78bb542f0538f8a3`, validated on 25 September 2026. [GitHub Actions run 36140729000](https://github.com/sinethxyz/continuity/actions/runs/36140729000) passed installation, compilation, targeted Ruff checks, the 51-test foundation/adapter/integrity subset, and the full 525-test regression suite. The selected tests are included in the total. The suite still emits existing warnings; passing tests are evidence for the exercised boundaries, not a production-readiness claim.

The adapter and integrity tests use real temporary Git repositories, worktree isolation, state observation, local artifact storage, patch capture/replay, and fresh-process journal reload. Model behaviour and verifier results remain deterministic test substitutes. This establishes a stronger systems integration boundary, not reliable live-model autonomy.

The reliability pass now preserves retrievable plans, patches, verification/review reports, and outcome records before cleanup; records failure paths; checks fresh state against supplied preconditions; and exercises replay/reload behavior. See [evidence-retention.md](docs/evidence-retention.md) for the exact scope and limitations.

## Run the tests

From a checked-out copy of this repository, with **Python 3.12+ and Git**:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"

# Selected transition and adapter tests.
python -m pytest -q tests/unit/test_transition_models.py tests/unit/runtime tests/unit/orchestration/test_agent_runner.py

# Full repository regression suite.
python -m pytest -q
```

These tests do not require live model calls or deployment. Installation downloads dependencies. The historical service setup is preserved in [LEGACY_FOUNDRY.md](LEGACY_FOUNDRY.md); it is separate from this test-only starting point.

## What this does not establish

This repository does not demonstrate a learned world model, general intelligence, or continual model learning. It does not establish crash-resume, exactly-once actions, comprehensive verification coverage, or production readiness.

The historical Git environment still starts from `HEAD` rather than honouring every requested base reference. Some verification and extraction paths are partial. `REQUEST_CHANGES` is advisory under the inherited Foundry policy, so an accepted transition is not necessarily an unconditional review approval. These are limitations to resolve, not details to hide behind a test count.

## Origin

I encountered the problem by trying to build the system.

While working on Unicorn, I was exploring how signals and evidence could become machine-readable state. UCF, initially called Unicorn Foundry, explored the complementary execution problem: plan a change, carry it out in an isolated environment, verify it, review it, and preserve a record of the result.

```text
Unicorn: signals → evidence → state → legibility
UCF:     state → intent → plan → action → verification → outcome
```

Unicorn was discontinued. The engineering question outlived the application that produced it.

Continuity is the public name for reopening that experiment. The origin was a practical systems problem; this framing is a later explanation of what I was trying to investigate. It is not a research-priority claim or an attempt to make the original implementation appear more complete than it was.

The earlier commits, [original architecture specification](docs/architecture.md), and [retrospective](RETROSPECTIVE.md) remain intact. [LEGACY_FOUNDRY.md](LEGACY_FOUNDRY.md) preserves the pre-Continuity README verbatim from the merged baseline, including its historical operational documentation. It is a snapshot, not an updated capability guarantee.

## Next milestones

The immediate sequence is to honour explicit base-reference requirements, make verification coverage and review acceptance unambiguous, and then converge the historical runtime onto the transition loop.

After that, longer-running, failure-injected and bounded live-model evaluations can test whether the architecture improves continuity in practice. Those evaluations have not been demonstrated here.

The implementation should earn broader claims rather than assume them in advance.

## Repository guide

```text
foundry/contracts/transition_models.py    state, evidence, actions, outcomes
foundry/runtime/                         generic transition loop and interfaces
foundry/adapters/                        historical Foundry compatibility bridge
foundry/environments/                    Git environment and observation
foundry/providers/                       provider interface and implementations
foundry/storage/                         artifact storage and outcome journal
foundry/orchestration/                   historical run lifecycle
app/ and workers/                       historical service entry points
tests/unit/runtime/                     transition and adapter tests
```

See the [architecture mapping](docs/ucf-architecture.md), [runtime decoupling audit](docs/runtime-decoupling-audit.md), and [publication notes](docs/publication.md) for the implementation history, migration boundaries, and approved public identity.

## Licence

Continuity is licensed under the **GNU Affero General Public License v3.0 only (AGPL-3.0-only)**.

Copyright © 2026 Sineth Madduma.

See [LICENSE](LICENSE) for the complete licence text. The AGPL includes source-availability obligations for modified versions offered to users over a network; anyone deploying or redistributing modified versions should review the licence terms that apply to their use.
