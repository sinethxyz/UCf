"""Tests for provider-neutral UCF transition contracts."""

from datetime import UTC, datetime

from foundry.contracts.transition_models import (
    EvidenceRef,
    StateSnapshot,
    TransitionObservation,
    TransitionOutcome,
    TransitionRequest,
)


def test_transition_contract_does_not_assume_unicorn_or_git() -> None:
    before = StateSnapshot(
        environment="warehouse-robot",
        observed_at=datetime.now(UTC),
        state={"location": "dock-a", "carrying": False},
        evidence=[
            EvidenceRef(
                kind="sensor",
                uri="sensor://robot/location",
                description="Position observation",
            )
        ],
    )
    request = TransitionRequest(
        environment="warehouse-robot",
        objective="move to dock-b",
        before_state=before,
    )

    after = StateSnapshot(
        environment=request.environment,
        observed_at=datetime.now(UTC),
        state={"location": "dock-b", "carrying": False},
    )
    observation = TransitionObservation(
        transition_id=request.id,
        observed_state=after,
    )
    outcome = TransitionOutcome(
        transition_id=request.id,
        accepted=True,
        before_state=before,
        after_state=after,
        observation=observation,
    )

    assert outcome.accepted is True
    assert outcome.after_state is not None
    assert outcome.after_state.state["location"] == "dock-b"
