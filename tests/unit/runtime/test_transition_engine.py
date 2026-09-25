"""Tests for the provider-neutral UCF transition engine."""

from datetime import UTC, datetime
from uuid import UUID

from foundry.contracts.transition_models import (
    ActionProposal,
    EvidenceRef,
    StateSnapshot,
    TransitionRequest,
    VerificationDecision,
)
from foundry.runtime.transition_engine import TransitionEngine


class FakeEnvironment:
    def __init__(self) -> None:
        self.cleaned = False

    async def prepare(
        self,
        target: str,
        base_ref: str,
        transition_id: UUID,
        transition_name: str,
    ) -> str:
        assert target == "warehouse-robot"
        assert base_ref == "current"
        assert transition_name
        return f"memory://{transition_id}"

    async def observe_changes(self, workspace: str) -> str:
        return ""

    async def cleanup(self, workspace: str) -> None:
        self.cleaned = True


class FakeObserver:
    def __init__(self) -> None:
        self.calls = 0

    async def observe(self, request: TransitionRequest, workspace: str) -> StateSnapshot:
        self.calls += 1
        location = "dock-a" if self.calls == 1 else "dock-b"
        return StateSnapshot(
            environment=request.environment,
            observed_at=datetime.now(UTC),
            state={"location": location},
        )


class FakePlanner:
    async def plan(
        self,
        request: TransitionRequest,
        current_state: StateSnapshot,
        workspace: str,
    ) -> ActionProposal:
        assert current_state.state["location"] == "dock-a"
        return ActionProposal(
            kind="move",
            description="Move the robot to dock-b",
            payload={"destination": "dock-b"},
        )


class FakeExecutor:
    async def execute(
        self,
        request: TransitionRequest,
        action: ActionProposal,
        workspace: str,
    ) -> list[EvidenceRef]:
        assert action.payload["destination"] == "dock-b"
        return [
            EvidenceRef(
                kind="action-log",
                uri=f"{workspace}/actions/1",
                description="Move command issued",
            )
        ]


class FakeVerifier:
    async def verify(
        self,
        request: TransitionRequest,
        before: StateSnapshot,
        after: StateSnapshot,
        action: ActionProposal,
        action_evidence: list[EvidenceRef],
    ) -> VerificationDecision:
        accepted = (
            before.state["location"] == "dock-a"
            and after.state["location"] == "dock-b"
            and bool(action_evidence)
        )
        return VerificationDecision(
            accepted=accepted,
            reason="Destination observed" if accepted else "Destination not observed",
            evidence=[
                EvidenceRef(
                    kind="verification",
                    uri="memory://verification/1",
                )
            ],
        )


async def test_transition_engine_closes_loop_without_unicorn_git_or_claude() -> None:
    environment = FakeEnvironment()
    engine = TransitionEngine(
        environment=environment,
        observer=FakeObserver(),
        planner=FakePlanner(),
        executor=FakeExecutor(),
        verifier=FakeVerifier(),
    )
    request = TransitionRequest(
        environment="warehouse-robot",
        objective="move to dock-b",
    )

    outcome = await engine.execute(request)

    assert outcome.accepted is True
    assert outcome.before_state is not None
    assert outcome.after_state is not None
    assert outcome.before_state.state["location"] == "dock-a"
    assert outcome.after_state.state["location"] == "dock-b"
    assert outcome.observation is not None
    assert len(outcome.observation.action_evidence) == 1
    assert len(outcome.observation.verification_evidence) == 1
    assert environment.cleaned is True
