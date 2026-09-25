"""Real-file journal tests; deterministic capabilities, no paid model calls."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from foundry.contracts.transition_models import (
    ActionProposal,
    EvidenceRef,
    StateSnapshot,
    TransitionOutcome,
    TransitionRequest,
    VerificationDecision,
)
from foundry.runtime.interfaces import TransitionJournal
from foundry.runtime.transition_engine import StateConflictError, TransitionEngine
from foundry.storage.artifact_store import ArtifactStore, ArtifactType
from foundry.storage.transition_journal import ArtifactStoreTransitionJournal


class FileWorld:
    """An actual persisted counter; observing cannot fabricate progress."""

    def __init__(self, root: Path, fail: str = "") -> None:
        self.root = root
        self.file = root / "world.json"
        if not self.file.exists():
            self.file.write_text("0", encoding="utf-8")
        self.fail = fail
        self.observations = 0
        self.executions = 0
        self.cleanups = 0
        self.workspace: Path | None = None

    def value(self) -> int:
        return int(self.file.read_text(encoding="utf-8"))

    async def prepare(
        self, target: str, base_ref: str, transition_id: UUID, transition_name: str,
    ) -> str:
        if self.fail == "prepare":
            raise RuntimeError("Synthetic prepare failure")
        self.workspace = self.root / str(transition_id)
        self.workspace.mkdir()
        return str(self.workspace)

    async def observe_changes(self, workspace: str) -> str:
        return str(self.value())

    async def cleanup(self, workspace: str) -> None:
        self.cleanups += 1
        if self.fail == "cleanup":
            raise OSError("Synthetic cleanup failure")
        shutil.rmtree(workspace)

    async def observe(self, request: TransitionRequest, workspace: str) -> StateSnapshot:
        self.observations += 1
        phase = {1: "observe_before", 2: "observe_after", 3: "observe_verified"}.get(
            self.observations
        )
        if self.fail == phase:
            raise RuntimeError("Synthetic observer failure")
        return StateSnapshot(
            environment="wrong" if self.fail == "wrong_environment" else request.environment,
            observed_at=datetime.now(UTC), state={"value": self.value()},
        )

    async def plan(
        self, request: TransitionRequest, current_state: StateSnapshot, workspace: str,
    ) -> ActionProposal:
        if self.fail == "plan":
            raise RuntimeError("Synthetic planner failure")
        if self.fail == "mutate_snapshot":
            current_state.state["value"] = 999
        return ActionProposal(kind="increment", description="Increment persisted counter")

    async def execute(
        self, request: TransitionRequest, action: ActionProposal, workspace: str,
    ) -> list[EvidenceRef]:
        self.executions += 1
        self.file.write_text(str(self.value() + 1), encoding="utf-8")
        if self.fail == "execute":
            raise RuntimeError("Synthetic error text must not enter persisted journal")
        if self.fail == "cancel":
            raise asyncio.CancelledError()
        return []

    async def verify(
        self, request: TransitionRequest, before: StateSnapshot, after: StateSnapshot,
        action: ActionProposal, action_evidence: list[EvidenceRef], workspace: str,
    ) -> VerificationDecision:
        if self.fail == "verify":
            raise RuntimeError("Synthetic verifier failure")
        if self.fail == "mutate_during_verify":
            self.file.write_text("100", encoding="utf-8")
        return VerificationDecision(
            accepted=self.fail != "reject" and after.state["value"] == before.state["value"] + 1,
            reason="Compared actual persisted states",
        )


def engine(world: FileWorld, journal: TransitionJournal) -> TransitionEngine:
    return TransitionEngine(world, world, world, world, world, journal)


def journal_at(root: Path) -> ArtifactStoreTransitionJournal:
    return ArtifactStoreTransitionJournal(ArtifactStore(str(root / "evidence")))


async def test_journal_reload_in_new_process_and_second_real_transition(tmp_path: Path) -> None:
    request = TransitionRequest(environment="counter", objective="increment")
    first = await engine(FileWorld(tmp_path), journal_at(tmp_path)).execute(request)
    assert first.accepted and first.after_state.state == {"value": 1}
    script = (
        "import asyncio,sys; from uuid import UUID; "
        "from foundry.storage.artifact_store import ArtifactStore; "
        "from foundry.storage.transition_journal import ArtifactStoreTransitionJournal; "
        "j=ArtifactStoreTransitionJournal(ArtifactStore(sys.argv[1])); "
        "print(asyncio.run(j.load(UUID(sys.argv[2]))).model_dump_json())"
    )
    process = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "evidence"), str(request.id)],
        check=True, capture_output=True, text=True,
    )
    loaded = TransitionOutcome.model_validate_json(process.stdout)
    second_request = TransitionRequest(
        environment="counter", objective="increment again", before_state=loaded.after_state,
    )
    second = await engine(FileWorld(tmp_path), journal_at(tmp_path)).execute(second_request)
    assert second.accepted
    assert second.before_state.state == {"value": 1}
    assert second.after_state.state == {"value": 2}
    assert (await journal_at(tmp_path).load(request.id)).after_state.state == {"value": 1}


@pytest.mark.parametrize("phase", [
    "prepare", "observe_before", "plan", "execute", "observe_after", "verify", "observe_verified",
])
async def test_each_processing_failure_is_recorded_and_not_cleaned(
    tmp_path: Path, phase: str,
) -> None:
    world = FileWorld(tmp_path, phase)
    request = TransitionRequest(environment="counter", objective="increment")
    with pytest.raises(RuntimeError):
        await engine(world, journal_at(tmp_path)).execute(request)
    record = await journal_at(tmp_path).load(request.id)
    assert record.accepted is False
    assert record.metadata["status"] == "failed"
    assert record.metadata["phase"] == phase
    assert record.metadata["error_type"] == "RuntimeError"
    assert world.cleanups == 0
    if phase != "prepare":
        assert Path(record.metadata["retained_workspace"]).is_dir()
    assert "Synthetic error text" not in record.model_dump_json()


async def test_cancellation_retains_partial_action_and_failure_record(tmp_path: Path) -> None:
    world = FileWorld(tmp_path, "cancel")
    request = TransitionRequest(environment="counter", objective="increment")
    with pytest.raises(asyncio.CancelledError):
        await engine(world, journal_at(tmp_path)).execute(request)
    record = await journal_at(tmp_path).load(request.id)
    assert record.metadata["status"] == "cancelled"
    assert not record.accepted and world.value() == 1 and world.cleanups == 0


async def test_stale_state_prevents_an_action(tmp_path: Path) -> None:
    world = FileWorld(tmp_path)
    stale = StateSnapshot(environment="counter", observed_at=datetime.now(UTC), state={"value": 7})
    request = TransitionRequest(environment="counter", objective="increment", before_state=stale)
    with pytest.raises(StateConflictError, match="stale"):
        await engine(world, journal_at(tmp_path)).execute(request)
    assert world.executions == 0 and world.value() == 0
    assert not (await journal_at(tmp_path).load(request.id)).accepted


async def test_wrong_environment_cannot_supply_state(tmp_path: Path) -> None:
    world = FileWorld(tmp_path, "wrong_environment")
    request = TransitionRequest(environment="counter", objective="increment")
    with pytest.raises(StateConflictError, match="different environment"):
        await engine(world, journal_at(tmp_path)).execute(request)
    assert world.executions == 0


async def test_verifier_mutation_invalidates_the_decision(tmp_path: Path) -> None:
    world = FileWorld(tmp_path, "mutate_during_verify")
    request = TransitionRequest(environment="counter", objective="increment")
    with pytest.raises(StateConflictError, match="during verification"):
        await engine(world, journal_at(tmp_path)).execute(request)
    assert world.value() == 100 and world.cleanups == 0
    assert not (await journal_at(tmp_path).load(request.id)).accepted


async def test_planner_cannot_mutate_recorded_before_snapshot(tmp_path: Path) -> None:
    world = FileWorld(tmp_path, "mutate_snapshot")
    result = await engine(world, journal_at(tmp_path)).execute(
        TransitionRequest(environment="counter", objective="increment")
    )
    assert result.accepted and result.before_state.state == {"value": 0}


async def test_rejection_is_not_exception_and_does_not_claim_rollback(tmp_path: Path) -> None:
    world = FileWorld(tmp_path, "reject")
    request = TransitionRequest(environment="counter", objective="increment")
    result = await engine(world, journal_at(tmp_path)).execute(request)
    assert not result.accepted and result.metadata["status"] == "rejected"
    assert world.value() == 1  # Rejected actions can still change reality.
    assert world.cleanups == 1
    assert (await journal_at(tmp_path).load(request.id)) == result


async def test_journal_failure_cannot_trigger_cleanup(tmp_path: Path) -> None:
    class BrokenJournal:
        async def record(self, outcome: TransitionOutcome) -> None:
            raise OSError("Synthetic persistence failure")

    world = FileWorld(tmp_path)
    with pytest.raises(OSError, match="persistence"):
        await engine(world, BrokenJournal()).execute(
            TransitionRequest(environment="counter", objective="increment")
        )
    assert world.cleanups == 0 and world.workspace.exists()


async def test_primary_error_survives_secondary_journal_error(tmp_path: Path) -> None:
    class BrokenJournal:
        async def record(self, outcome: TransitionOutcome) -> None:
            raise OSError("Synthetic persistence failure")

    world = FileWorld(tmp_path, "execute")
    with pytest.raises(RuntimeError) as caught:
        await engine(world, BrokenJournal()).execute(
            TransitionRequest(environment="counter", objective="increment")
        )
    assert any("Failure journal also failed: OSError" in note for note in caught.value.__notes__)
    assert world.cleanups == 0


async def test_cleanup_failure_preserves_decision_and_records_warning(tmp_path: Path) -> None:
    world = FileWorld(tmp_path, "cleanup")
    request = TransitionRequest(environment="counter", objective="increment")
    result = await engine(world, journal_at(tmp_path)).execute(request)
    assert result.accepted and result.metadata["cleanup_status"] == "failed"
    loaded = await journal_at(tmp_path).load(request.id)
    assert loaded == result and Path(loaded.metadata["retained_workspace"]).exists()


async def test_atomic_write_failure_preserves_previous_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ArtifactStore(str(tmp_path / "artifacts"))
    identity = uuid4()
    old = await store.store(identity, ArtifactType.TRANSITION, b"previous")

    def refuse_replace(*args: object) -> None:
        raise OSError("Synthetic replace failure")

    monkeypatch.setattr("foundry.storage.artifact_store.os.replace", refuse_replace)
    with pytest.raises(OSError):
        await store.store(identity, ArtifactType.TRANSITION, b"replacement")
    assert await store.retrieve(old["storage_path"]) == b"previous"
    assert len(await store.list_artifacts(identity)) == 1


async def test_journal_refuses_corrupt_or_wrong_identity(tmp_path: Path) -> None:
    journal = journal_at(tmp_path)
    identity = uuid4()
    await journal.artifact_store.store(
        identity, ArtifactType.TRANSITION, "{", "transition_outcome.json",
    )
    with pytest.raises(ValidationError):
        await journal.load(identity)
    other = TransitionOutcome(transition_id=uuid4(), accepted=False)
    await journal.artifact_store.store(
        identity, ArtifactType.TRANSITION, other.model_dump_json(), "transition_outcome.json"
    )
    with pytest.raises(ValueError, match="different transition ID"):
        await journal.load(identity)
