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

## Owner-admin actions still required

The available GitHub connection supports repository files and PRs, but does not expose a repository rename or About/topics update action. Those settings have not been changed by this documentation pass.

Apply the repository name, About description, and topics above using the owner's GitHub controls, confirming that the chosen name is available. Keep the existing visibility; this pass does not request a visibility change. Do not invent a project homepage or package URL.

After the rename, verify the canonical repository URL, old inbound links, open PRs, and any relevant integrations. Update local Git remotes after confirming the new URL. Do not create a replacement repository or discard the existing history.

Repository settings are separate from Git commits; putting `Continuity` in the README cannot rename the repository.

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
| Merged main `2639b8e` | Transition foundation and Foundry adapter | 495 full-suite tests; 21 selected tests included in the total |
| Open [PR #6](https://github.com/sinethxyz/UCf/pull/6), head `8a421e5` | Evidence retention, failure records, state checks, reload/replay tests | 525 full-suite tests; 51 selected tests included in the total |
| This public-introduction branch | Naming and documentation only | No new runtime capability or model evaluation |

Sources: [baseline CI](https://github.com/sinethxyz/UCf/actions/runs/36120929154) and [PR #6 CI](https://github.com/sinethxyz/UCf/actions/runs/36138567006). Both test runs reported 2,774 warnings. Recheck the actual publication revision before using any count in an announcement.

The pending PR's code and test evidence do not belong to main until that PR is approved and merged. Keep this rebrand separate from that approval. Renaming the repository does not fix the base-reference limitation, complete verifier coverage, migrate RunEngine, or provide crash recovery.

## Licence decision

The pre-rebrand README says: **Internal use only. Not licensed for external distribution.** This pass preserves that notice and does not choose a new licence.

Before presenting this as an open-source release or inviting external reuse, the owner must explicitly decide the licensing terms. Do not add an MIT, Apache, or other licence merely because the repository is public.

## Launch checklist

- [ ] Apply and verify the repository name and About/topics settings.
- [ ] Review and approve the documentation-only rebrand separately; no merge is performed by this pass.
- [ ] Review PR #6 separately; leave it unmerged until explicitly approved.
- [ ] Resolve the public-release/reuse licence decision.
- [ ] Recheck the final published commit, links, CI evidence, and capability statements.
- [ ] Publish the announcement only after the desired public state is confirmed.
