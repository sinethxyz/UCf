# UCF Retrospective

## Why this document exists

UCF did not begin as an attempt to propose a general theory of machine intelligence.

It began as an engineering response to a practical problem.

While building Unicorn, I was trying to make a changing environment legible to software through signals, evidence, and explicit state. Once that representation existed, another problem appeared: a capable model could still behave discontinuously across time.

It could produce a good plan without preserving why the plan existed. It could make a change without establishing whether the environment actually reached the intended state. It could observe an outcome without turning that outcome into durable state for the next operation.

UCF, then called Unicorn Foundry, was an attempt to build the infrastructure around that boundary.

## The original split

The original conceptual split was approximately:

```text
Unicorn
world → signals → evidence → state → legibility

UCF
state → intent → plan → execution → verification → outcome
```

The useful unit was therefore larger than a model call.

```text
STATE(t)
   ↓
reason
   ↓
intent
   ↓
action
   ↓
consequence
   ↓
observation
   ↓
evidence
   ↓
STATE(t+1)
```

The implementation expressed only part of this larger loop, and it expressed that part through the concrete environment available at the time: software repositories, Claude, Git worktrees, pull requests, tests, schemas, artifacts, PostgreSQL, Redis, and deterministic hooks.

## What was actually built

The repository contains real implementations of several mechanisms that matter to the original question:

- explicit run states and legal transitions;
- persistent events and run metadata;
- isolated worktrees;
- structured plan artifacts;
- implementation and provider boundaries;
- deterministic verification;
- independent review;
- durable artifacts;
- cancellation, retry, and failure paths;
- evidence/extraction contracts;
- evaluation scaffolding.

It also contains planned or partial surfaces. Some task paths remain unimplemented, and the architecture document describes more than the runtime currently completes.

That distinction matters. This retrospective is not intended to make the historical implementation appear more complete than it was.

## What I understand differently now

The most useful way I now understand the experiment is as a distinction between **intelligence at an instant** and **intelligence through time**.

A capable model can map context to an impressive output. Persistent operation asks for more:

- What is currently believed to be true?
- What evidence supports that state?
- What changed since the previous operation?
- What is the intended transition?
- What action was actually taken?
- What consequence followed?
- How was the consequence verified?
- What should become durable state for the next operation?

Those questions are systems questions even when an intelligent model participates in answering them.

This is why UCF should not be architecturally synonymous with Claude, agents, coding, or GitHub. Those were components of its first environment.

## What UCF is not

UCF is not presented as a learned world model.

It is not a claim that software orchestration solves intelligence.

It is not a claim that explicit state can replace learned representations, perception, planning, or adaptation.

It is not a retrospective claim to ideas that were not present in the original work.

The narrower claim is historical and architectural:

> While trying to build a system that could operate coherently for longer than a single model interaction, I independently encountered the problem that model capability alone did not provide state, consequence, verification, or continuity. UCF was an attempt to build some of that surrounding infrastructure.

## Why reopen it

Unicorn has been discontinued, but the problem that produced UCF remains useful.

The next phase is therefore not to revive Unicorn. It is to extract the general mechanisms from the historical Foundry implementation and ask which of them survive when the original assumptions are removed.

The working question is:

> **What must exist around an intelligent model for it to remain coherent while the environment it operates in changes?**

The implementation should earn increasingly general answers to that question rather than assuming them in advance.

## Preservation rule

The existing Git history is part of the evidence.

Historical commits should remain intact. New documentation should distinguish original implementation, later interpretation, and future direction rather than rewriting one as another.

UCF should become more general by evolution, not by pretending it always was.
