# Evidence retention before runtime convergence

Engineering pass: 25 September 2026. Audited baseline:
`2639b8ebeeb485950a8faed17491b03ff440b354` (after PR #5).
This is new implementation work, not a claim about the original experiment.

## The gap

The first adapter stored an outcome containing a patch checksum, but not the
patch itself. It then deleted the worktree. A fingerprint was therefore being
used where retrievable evidence was needed. Processing exceptions also bypassed
outcome journaling, and a supplied before-state bypassed fresh observation.
Passing the earlier tests did not establish those properties.

## This change

`FoundryTransitionRuntime` now wires the artifact store into its planner,
executor and verifier. It saves the plan before implementation, independently
captures and saves the real Git-visible patch, and stores complete verification
and review reports. Outcome references contain retrievable `artifact://runs/...`
paths and checksums. Individual adapters retain an optional non-persisting mode
for compatibility; use the runtime factory for the evidence-preserving path.

Git capture uses a temporary index rather than changing the real staging area.
It includes tracked edits/deletions and non-ignored additions, including binary
patches and literal filenames. The observer and executor use the same capture
mechanism. The persistent verifier checks the stored patch against the workspace
rather than trusting the agent's returned diff. An executor that changes HEAD
is rejected for inspection, with its workspace retained.

The transition engine freshly observes before-state even when a prior snapshot
is supplied. That supplied snapshot is an explicit precondition. It checks
observation environment identity and detects state changes during verification.
Snapshot `state` must therefore be a stable, comparable representation; this is
not a proof that an arbitrary representation is accurate or complete.

Processing failures and cooperative cancellation attempt to journal an
unaccepted outcome with phase, exception type, and retained workspace. Raw
exception messages are not copied into that record. The original exception is
re-raised. If journaling also fails, the original exception gains an explicit
note; no durable record is claimed. No automatic retry or destructive cleanup
is attempted on these paths.

A normal decision is journaled before cleanup. Cleanup errors are recorded as
resource warnings without converting a verified decision into a different
verdict. Atomic same-filesystem artifact replacement avoids exposing partial
new files, and `ArtifactStoreTransitionJournal.load()` allows a new process to
read and validate an outcome. This is local persistence, not an execution log
with exactly-once or crash-resume guarantees.

## Evidence to run

```bash
pytest -q tests/unit/runtime/test_transition_integrity.py \
  tests/unit/runtime/test_git_evidence_retention.py
pytest -q
```

The new tests use actual files and Git repositories. They cover two counter
transitions separated by a fresh-process journal reload; stale/wrong state;
failures across processing phases; cancellation and cleanup/persistence errors;
atomic-write failure; verifier mutation; and patch replay after worktree removal.
Patch tests include staged edits, deletion, binary additions, spaces, newlines,
and literal pathspec-shaped names. Model behavior is deterministic test code,
not a live LLM evaluation. The full regression suite remains the compatibility
gate; a count of tests is not a completeness or production-readiness claim.

## Still not established

- The historical WorktreeManager still creates from HEAD and ignores the
  adapter's requested base_ref. Fix and test that before runtime convergence.
- The historical RunEngine has not been routed through this path. PR creation,
  adoption of a worktree result, and deployment remain separate. A saved patch
  is not an applied change in the source repository.
- Historical verifier coverage and REQUEST_CHANGES-as-advisory policy remain.
  An accepted outcome is not a claim of comprehensive verification or approval
  for production publication.
- Abrupt process death, concurrent execution, duplicate transition IDs,
  distributed storage, and exactly-once actions are not solved here. Outcome
  records can be replaced under the same ID; do not retry blindly.
- Ignored files, external LFS objects and submodule contents are not a
  self-contained workspace backup. Git filters are not sandboxed. The
  secret-shaped filename check is not a content-based secret scanner.
- Retained workspaces consume resources and require explicit inspection and
  cleanup. Keeping evidence is not rollback.

These limitations are prerequisites for the convergence plan in
[runtime-decoupling-audit.md](runtime-decoupling-audit.md), not reasons to rename
or rewrite the historical implementation again.
