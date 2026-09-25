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

**Merged baseline:** commit `2639b8ebeeb485950a8faed17491b03ff440b354`, validated on 25 September 2026. [GitHub Actions run 36120929154](https://github.com/sinethxyz/UCf/actions/runs/36120929154) passed installation, compilation, targeted Ruff checks, 21 selected foundation/adapter tests, and the full 495-test suite. The selected tests are included in the total. The suite emitted 2,774 warnings.

The adapter integration test uses a real temporary Git repository, real worktree isolation, real state observation, and local outcome storage. Model behaviour and verifier results are deterministic test substitutes. This establishes an integration boundary, not reliable live-model autonomy.

**Pending reliability work:** [PR #6](https://github.com/sinethxyz/UCf/pull/6) preserves retrievable patches and reports before cleanup, adds failure records and fresh-state checks, and tests journal reload and patch replay. Its branch passed 525 tests, including a 51-test selected subset, in [run 36138567006](https://github.com/sinethxyz/UCf/actions/runs/36138567006). At preparation of this introduction, that PR is **open and unmerged**. Those improvements must not be attributed to the merged baseline.

In particular, the baseline adapter can retain a patch checksum without retaining the patch itself before cleanup. That gap is one reason the evidence-retention work must precede claims about durable continuation.

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

The immediate sequence is to review the pending evidence-retention work, honour explicit base-state requirements, make verification coverage and review acceptance unambiguous, and then converge the historical runtime onto the transition loop.

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

The existing notice remains: **Internal use only. Not licensed for external distribution.**

This naming and documentation pass does not grant a new licence. A public-release/reuse licence requires a separate owner decision; the project is not being announced as open source in this pass.
