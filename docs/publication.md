# Continuity: publication notes

Prepared 25 September 2026. These are the approved public identity and launch boundaries, not confirmation that GitHub settings have been changed or an announcement has been posted.

## Identity

**Display name:** Continuity

**Repository name:** `continuity`

**Intended repository:** `sinethxyz/continuity`

**GitHub About description:**

> An experimental runtime for persistent machine intelligence across state, action, verification, and time.

**README tagline:**

> An experiment in intelligence through time.

**Core sentence:**

> The model is a participant in the loop, not the loop itself.

**Topics:**

```text
ai
agents
state-machines
llm
agent-infrastructure
ai-systems
orchestration
verification
continuity
machine-intelligence
```

Persistent machine intelligence describes the research objective. The evidence currently supports a software-systems experiment with scoped tests, not a proven general or continuously learning intelligence.

## Naming boundary

Continuity is the public name. UCF and Unicorn Foundry remain historical names. Do not relabel the original commits or retrofit dates into the origin story. The claim is that the engineering problem was encountered while building the system, not that this work originated another researcher's architecture.

Python imports stay under `foundry`. The distribution stays `unicorn-foundry`. Environment variable prefixes, workflow identifiers, historical specifications, and internal contracts are unchanged. There is no new package release in this naming pass.

[LEGACY_FOUNDRY.md](../LEGACY_FOUNDRY.md) preserves the old README verbatim from commit `2639b8ebeeb485950a8faed17491b03ff440b354` (blob `7caeb132210e40d8f98ed587204eef41cb03d2dd`). Its root location preserves the original relative links.

## Repository settings

The repository has been renamed to `sinethxyz/continuity`, and the approved About description and topics have been applied by the owner.

The existing Git history is preserved. Local clones should use the canonical remote `https://github.com/sinethxyz/continuity.git`.

## Draft announcement

Not posted. Add the verified repository URL when publishing.

> The model is not the system.
>
> While building Unicorn + UCF, I kept encountering the same problem: a capable model could still sit inside a discontinuous system.
>
> I'm reopening that experiment as Continuity: a systems experiment in explicit state, controlled action, verification, and what survives the next interaction.
>
> The model is a participant in the loop, not the loop itself.

Do not add claims about being first, a learned world model, general intelligence, production readiness, or a year of development without supporting dated artifacts. Do not describe deterministic model substitutes as live-model validation.

## Evidence boundaries

At preparation:

| Revision | Scope | Evidence |
| --- | --- | --- |
| Merged main `6cc52e5` | Transition foundation, Foundry adapter, evidence retention, failure records, state checks, reload/replay tests | 525 full-suite tests; 51 selected tests included in the total |
| This public-introduction branch | Naming, licensing and documentation | No new model capability or deployment |

Source: [main CI](https://github.com/sinethxyz/continuity/actions/runs/36140729000). The run completed successfully on the merged reliability baseline. Recheck the final publication revision before quoting test counts.

Renaming and licensing the repository do not fix the base-reference limitation, complete verifier coverage, migrate RunEngine, provide crash recovery, or establish production readiness.

## Licence

The owner selected **GNU Affero General Public License v3.0 only (AGPL-3.0-only)** for Continuity. The repository includes the complete licence text in `LICENSE`; package metadata uses the same SPDX expression.

The pre-rebrand `LEGACY_FOUNDRY.md` remains a historical snapshot and may contain the former internal-use notice. That snapshot does not override the current root licence.

## Launch checklist

- [x] Apply and verify the repository name and About/topics settings.
- [x] Merge and validate the evidence-retention reliability pass.
- [x] Select AGPL-3.0-only and add repository/package licence metadata.
- [ ] Recheck the final public-introduction merge commit, links, CI evidence, and capability statements.
- [ ] Publish the announcement only after the desired public state is confirmed.
