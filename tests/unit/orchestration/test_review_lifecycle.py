"""Tests for the review lifecycle in _run_review().

Validates state transitions, artifact storage, run events, error handling,
and verdict-driven behavior for APPROVE, REJECT, and REQUEST_CHANGES paths.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from foundry.contracts.review_models import ReviewIssue, ReviewVerdict
from foundry.contracts.shared import (
    MCPProfile,
    ReviewSeverity,
    ReviewVerdictType,
    RunState,
    TaskType,
)
from foundry.contracts.task_types import TaskRequest
from foundry.db.queries.artifacts import get_artifacts
from foundry.db.queries.runs import create_run, get_run, get_run_events
from foundry.orchestration.run_engine import VALID_TRANSITIONS, RunEngine
from foundry.storage.artifact_store import ArtifactStore, ArtifactType


# ---------------------------------------------------------------------------
# Shared constants and helpers
# ---------------------------------------------------------------------------


SAMPLE_DIFF = """\
diff --git a/services/api/search/handler.go b/services/api/search/handler.go
--- a/services/api/search/handler.go
+++ b/services/api/search/handler.go
@@ -10,7 +10,7 @@
-    offset := (page - 1) * pageSize + 1
+    offset := (page - 1) * pageSize
diff --git a/services/api/search/handler_test.go b/services/api/search/handler_test.go
--- a/services/api/search/handler_test.go
+++ b/services/api/search/handler_test.go
@@ -100,6 +100,20 @@
+func TestSearch_Pagination_FirstPageOffset(t *testing.T) {
+    // regression test for off-by-one
+}
"""


def _make_engine(
    session: AsyncSession,
    artifact_store: ArtifactStore,
    agent_runner: MagicMock,
) -> RunEngine:
    """Create a RunEngine with session, artifact_store, and agent_runner wired."""
    return RunEngine(
        session=session,
        artifact_store=artifact_store,
        worktree_manager=MagicMock(),
        agent_runner=agent_runner,
        pr_creator=MagicMock(),
        verification_runner=MagicMock(),
    )


async def _setup_run_in_verification_passed_state(
    session: AsyncSession,
    engine: RunEngine,
    task_request: TaskRequest,
) -> UUID:
    """Create a run and advance it to VERIFICATION_PASSED state."""
    run = await create_run(session, task_request)
    run_id = run.id

    transitions = [
        (RunState.QUEUED, RunState.CREATING_WORKTREE),
        (RunState.CREATING_WORKTREE, RunState.PLANNING),
        (RunState.PLANNING, RunState.IMPLEMENTING),
        (RunState.IMPLEMENTING, RunState.VERIFYING),
        (RunState.VERIFYING, RunState.VERIFICATION_PASSED),
    ]
    for from_s, to_s in transitions:
        await engine._transition(run_id, from_s, to_s, f"{from_s.value} -> {to_s.value}")

    return run_id


def _make_approve_verdict() -> ReviewVerdict:
    return ReviewVerdict(
        verdict=ReviewVerdictType.APPROVE,
        issues=[],
        summary="Clean change, no issues found.",
        confidence=0.92,
    )


def _make_reject_verdict() -> ReviewVerdict:
    return ReviewVerdict(
        verdict=ReviewVerdictType.REJECT,
        issues=[
            ReviewIssue(
                severity=ReviewSeverity.CRITICAL,
                file_path="services/api/search/handler.go",
                line_range="10-10",
                description="Pagination offset will skip first page of results",
                suggestion="Use (page - 1) * pageSize instead",
            ),
        ],
        summary="Critical pagination bug makes the change unsafe to ship.",
        confidence=0.95,
    )


def _make_request_changes_verdict() -> ReviewVerdict:
    return ReviewVerdict(
        verdict=ReviewVerdictType.REQUEST_CHANGES,
        issues=[
            ReviewIssue(
                severity=ReviewSeverity.MAJOR,
                file_path="services/api/search/handler.go",
                line_range="15-20",
                description="Missing bounds check on page parameter",
                suggestion="Validate page >= 1 before computing offset",
            ),
            ReviewIssue(
                severity=ReviewSeverity.MINOR,
                file_path="services/api/search/handler_test.go",
                line_range="100-102",
                description="Test body is empty — add assertions",
            ),
        ],
        summary="Functional change is sound but needs input validation and test coverage.",
        confidence=0.85,
    )


def _make_agent_runner(verdict: ReviewVerdict) -> MagicMock:
    """Create a mock AgentRunner whose run_reviewer returns the given verdict."""
    runner = MagicMock()
    runner.run_reviewer = AsyncMock(return_value=verdict)
    return runner


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_task_request() -> TaskRequest:
    return TaskRequest(
        task_type=TaskType.BUG_FIX,
        repo="unicorn-app",
        base_branch="main",
        title="Fix pagination bug",
        prompt="Fix the off-by-one error in search pagination",
        target_paths=["services/api/search/handler.go"],
        mcp_profile=MCPProfile.NONE,
    )


@pytest.fixture
def artifact_store(tmp_path: Path) -> ArtifactStore:
    return ArtifactStore(base_path=str(tmp_path / "artifacts"))


@pytest.fixture
def approve_runner() -> MagicMock:
    return _make_agent_runner(_make_approve_verdict())


@pytest.fixture
def reject_runner() -> MagicMock:
    return _make_agent_runner(_make_reject_verdict())


@pytest.fixture
def request_changes_runner() -> MagicMock:
    return _make_agent_runner(_make_request_changes_verdict())


# ---------------------------------------------------------------------------
# Test approve path
# ---------------------------------------------------------------------------


class TestReviewApprovePath:
    """Review approves -> stays in REVIEWING (ready for PR), artifacts stored, events emitted."""

    async def test_returns_approve_verdict(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        approve_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, approve_runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, sample_task_request,
        )

        result = await engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        assert isinstance(result, ReviewVerdict)
        assert result.verdict == ReviewVerdictType.APPROVE

    async def test_transitions_to_reviewing(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        approve_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, approve_runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, sample_task_request,
        )

        await engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        run = await get_run(async_session, run_id)
        assert run is not None
        # APPROVE stays in REVIEWING — caller (_open_pr) handles next transition
        assert run.state == RunState.REVIEWING.value

    async def test_does_not_set_error_message(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        approve_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, approve_runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, sample_task_request,
        )

        await engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        run = await get_run(async_session, run_id)
        assert run is not None
        assert run.error_message is None

    async def test_emits_reviewing_event(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        approve_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, approve_runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, sample_task_request,
        )

        await engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        events = await get_run_events(async_session, run_id)
        event_states = [e.state for e in events]
        assert "reviewing" in event_states

    async def test_emits_review_complete_event_with_summary(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        approve_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, approve_runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, sample_task_request,
        )

        await engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        events = await get_run_events(async_session, run_id)
        review_events = [
            e for e in events
            if e.state == "reviewing" and "Review complete" in e.message
        ]
        assert len(review_events) == 1
        msg = review_events[0].message
        assert "approve" in msg
        assert "issues: 0" in msg
        assert "confidence: 0.92" in msg

    async def test_passes_changed_files_to_reviewer(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        approve_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, approve_runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, sample_task_request,
        )

        await engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        call_kwargs = approve_runner.run_reviewer.call_args.kwargs
        assert "services/api/search/handler.go" in call_kwargs["changed_files"]
        assert "services/api/search/handler_test.go" in call_kwargs["changed_files"]

    async def test_passes_pr_title_to_reviewer(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        approve_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, approve_runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, sample_task_request,
        )

        await engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        call_kwargs = approve_runner.run_reviewer.call_args.kwargs
        assert call_kwargs["pr_title"] == "[Foundry] bug_fix: Fix pagination bug"

    async def test_pr_description_contains_prompt_and_changed_files(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        approve_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, approve_runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, sample_task_request,
        )

        await engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        call_kwargs = approve_runner.run_reviewer.call_args.kwargs
        desc = call_kwargs["pr_description"]
        assert "off-by-one" in desc
        assert "Changed files:" in desc


# ---------------------------------------------------------------------------
# Test reject path
# ---------------------------------------------------------------------------


class TestReviewRejectPath:
    """Review rejects -> REVIEW_FAILED, error_message set, no PR."""

    async def test_returns_reject_verdict(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        reject_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, reject_runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, sample_task_request,
        )

        result = await engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        assert isinstance(result, ReviewVerdict)
        assert result.verdict == ReviewVerdictType.REJECT

    async def test_transitions_to_review_failed(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        reject_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, reject_runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, sample_task_request,
        )

        await engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        run = await get_run(async_session, run_id)
        assert run is not None
        assert run.state == RunState.REVIEW_FAILED.value

    async def test_sets_error_message_with_rejection_summary(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        reject_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, reject_runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, sample_task_request,
        )

        await engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        run = await get_run(async_session, run_id)
        assert run is not None
        assert run.error_message is not None
        assert "Review rejected" in run.error_message
        assert "pagination bug" in run.error_message

    async def test_emits_reviewing_and_review_failed_events(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        reject_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, reject_runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, sample_task_request,
        )

        await engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        events = await get_run_events(async_session, run_id)
        event_states = [e.state for e in events]
        assert "reviewing" in event_states
        assert "review_failed" in event_states

    async def test_review_failed_event_contains_rejection_reason(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        reject_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, reject_runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, sample_task_request,
        )

        await engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        events = await get_run_events(async_session, run_id)
        fail_events = [e for e in events if e.state == "review_failed"]
        assert len(fail_events) == 1
        assert "Review rejected" in fail_events[0].message

    async def test_review_complete_event_has_reject_verdict(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        reject_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, reject_runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, sample_task_request,
        )

        await engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        events = await get_run_events(async_session, run_id)
        review_events = [
            e for e in events
            if e.state == "reviewing" and "Review complete" in e.message
        ]
        assert len(review_events) == 1
        msg = review_events[0].message
        assert "reject" in msg
        assert "issues: 1" in msg
        assert "confidence: 0.95" in msg


# ---------------------------------------------------------------------------
# Test request_changes path
# ---------------------------------------------------------------------------


class TestReviewRequestChangesPath:
    """Review requests changes -> stays in REVIEWING (advisory), PR proceeds."""

    async def test_returns_request_changes_verdict(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        request_changes_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, request_changes_runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, sample_task_request,
        )

        result = await engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        assert isinstance(result, ReviewVerdict)
        assert result.verdict == ReviewVerdictType.REQUEST_CHANGES

    async def test_stays_in_reviewing_state(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        request_changes_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, request_changes_runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, sample_task_request,
        )

        await engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        run = await get_run(async_session, run_id)
        assert run is not None
        # REQUEST_CHANGES stays in REVIEWING — PR still opens
        assert run.state == RunState.REVIEWING.value

    async def test_does_not_set_error_message(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        request_changes_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, request_changes_runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, sample_task_request,
        )

        await engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        run = await get_run(async_session, run_id)
        assert run is not None
        assert run.error_message is None

    async def test_emits_advisory_event_for_pr_comments(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        request_changes_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, request_changes_runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, sample_task_request,
        )

        await engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        events = await get_run_events(async_session, run_id)
        advisory_events = [
            e for e in events
            if "requested changes" in e.message.lower()
            and "PR will include" in e.message
        ]
        assert len(advisory_events) == 1
        assert "2 issues" in advisory_events[0].message

    async def test_review_complete_event_has_request_changes_verdict(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        request_changes_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, request_changes_runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, sample_task_request,
        )

        await engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        events = await get_run_events(async_session, run_id)
        review_events = [
            e for e in events
            if e.state == "reviewing" and "Review complete" in e.message
        ]
        assert len(review_events) == 1
        msg = review_events[0].message
        assert "request_changes" in msg
        assert "issues: 2" in msg
        assert "confidence: 0.85" in msg

    async def test_does_not_transition_to_review_failed(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        request_changes_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, request_changes_runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, sample_task_request,
        )

        await engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        events = await get_run_events(async_session, run_id)
        event_states = [e.state for e in events]
        assert "review_failed" not in event_states


# ---------------------------------------------------------------------------
# Test artifact storage
# ---------------------------------------------------------------------------


class TestReviewArtifactStorage:
    """review.json is stored for all verdict types."""

    async def test_stores_review_json_artifact(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        approve_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, approve_runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, sample_task_request,
        )

        await engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        artifacts = await artifact_store.list_artifacts(run_id)
        review_artifacts = [a for a in artifacts if "review" in a["filename"]]
        assert len(review_artifacts) == 1
        assert "review.json" in review_artifacts[0]["filename"]

    async def test_review_json_contains_verdict_data(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        reject_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, reject_runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, sample_task_request,
        )

        await engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        artifacts = await artifact_store.list_artifacts(run_id)
        review_artifacts = [a for a in artifacts if "review" in a["filename"]]
        storage_path = f"runs/{run_id}/{review_artifacts[0]['filename']}"
        content = json.loads(await artifact_store.retrieve(storage_path))

        assert content["verdict"] == "reject"
        assert len(content["issues"]) == 1
        assert content["confidence"] == 0.95
        assert "pagination bug" in content["summary"]

    async def test_registers_artifact_in_db_with_checksum(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        approve_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, approve_runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, sample_task_request,
        )

        await engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        db_artifacts = await get_artifacts(async_session, run_id)
        review_db = [a for a in db_artifacts if a.artifact_type == "review"]
        assert len(review_db) == 1
        assert review_db[0].checksum is not None
        assert review_db[0].size_bytes is not None
        assert review_db[0].size_bytes > 0

    async def test_stores_artifact_on_reject(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        reject_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        """review.json is stored even when review rejects."""
        engine = _make_engine(async_session, artifact_store, reject_runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, sample_task_request,
        )

        await engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        db_artifacts = await get_artifacts(async_session, run_id)
        review_db = [a for a in db_artifacts if a.artifact_type == "review"]
        assert len(review_db) == 1

    async def test_stores_artifact_on_request_changes(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        request_changes_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        """review.json is stored for request_changes verdict."""
        engine = _make_engine(async_session, artifact_store, request_changes_runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, sample_task_request,
        )

        await engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        artifacts = await artifact_store.list_artifacts(run_id)
        review_artifacts = [a for a in artifacts if "review" in a["filename"]]
        assert len(review_artifacts) == 1

        storage_path = f"runs/{run_id}/{review_artifacts[0]['filename']}"
        content = json.loads(await artifact_store.retrieve(storage_path))
        assert content["verdict"] == "request_changes"
        assert len(content["issues"]) == 2

    async def test_artifact_checksum_matches_content(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        approve_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        engine = _make_engine(async_session, artifact_store, approve_runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, sample_task_request,
        )

        await engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        db_artifacts = await get_artifacts(async_session, run_id)
        review_db = [a for a in db_artifacts if a.artifact_type == "review"]
        stored_checksum = review_db[0].checksum

        artifacts = await artifact_store.list_artifacts(run_id)
        review_artifacts = [a for a in artifacts if "review" in a["filename"]]
        storage_path = f"runs/{run_id}/{review_artifacts[0]['filename']}"
        raw = await artifact_store.retrieve(storage_path)
        expected_checksum = artifact_store.get_checksum(raw)

        assert stored_checksum == expected_checksum


# ---------------------------------------------------------------------------
# Test state transitions
# ---------------------------------------------------------------------------


class TestReviewStateTransitions:
    """State machine correctness for the review lifecycle."""

    async def test_verification_passed_to_reviewing_transition(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        approve_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        """_run_review transitions from VERIFICATION_PASSED to REVIEWING first."""
        engine = _make_engine(async_session, artifact_store, approve_runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, sample_task_request,
        )

        await engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        events = await get_run_events(async_session, run_id)
        event_states = [e.state for e in events]
        assert "reviewing" in event_states

    async def test_full_reject_transition_chain(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        reject_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        """VERIFICATION_PASSED -> REVIEWING -> REVIEW_FAILED on reject."""
        engine = _make_engine(async_session, artifact_store, reject_runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, sample_task_request,
        )

        await engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        run = await get_run(async_session, run_id)
        assert run.state == RunState.REVIEW_FAILED.value

        events = await get_run_events(async_session, run_id)
        event_states = [e.state for e in events]
        # reviewing must come before review_failed
        idx_reviewing = next(
            i for i, s in enumerate(event_states)
            if s == "reviewing"
        )
        idx_failed = event_states.index("review_failed")
        assert idx_reviewing < idx_failed

    async def test_review_failed_only_allows_retry(self):
        """REVIEW_FAILED can only transition back to QUEUED (retry)."""
        allowed = VALID_TRANSITIONS[RunState.REVIEW_FAILED]
        assert allowed == {RunState.QUEUED}

    async def test_review_failed_is_retryable(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        reject_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        """A run in REVIEW_FAILED state can be retried back to QUEUED."""
        engine = _make_engine(async_session, artifact_store, reject_runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, sample_task_request,
        )

        await engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        response = await engine.retry_run(run_id)
        assert response.state == RunState.QUEUED

    async def test_review_failed_is_terminal_for_run(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        reject_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        """REVIEW_FAILED cannot transition to PR_OPENED or COMPLETED."""
        allowed = VALID_TRANSITIONS[RunState.REVIEW_FAILED]
        assert RunState.PR_OPENED not in allowed
        assert RunState.COMPLETED not in allowed
        assert RunState.REVIEWING not in allowed

    async def test_approve_allows_pr_transition(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        approve_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        """After APPROVE, run is in REVIEWING which can transition to PR_OPENED."""
        engine = _make_engine(async_session, artifact_store, approve_runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, sample_task_request,
        )

        await engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        run = await get_run(async_session, run_id)
        assert run.state == RunState.REVIEWING.value
        assert RunState.PR_OPENED in VALID_TRANSITIONS[RunState.REVIEWING]

    async def test_request_changes_allows_pr_transition(
        self,
        async_session: AsyncSession,
        artifact_store: ArtifactStore,
        request_changes_runner: MagicMock,
        sample_task_request: TaskRequest,
    ):
        """After REQUEST_CHANGES, run stays in REVIEWING and can transition to PR_OPENED."""
        engine = _make_engine(async_session, artifact_store, request_changes_runner)
        run_id = await _setup_run_in_verification_passed_state(
            async_session, engine, sample_task_request,
        )

        await engine._run_review(run_id, SAMPLE_DIFF, sample_task_request)

        run = await get_run(async_session, run_id)
        assert run.state == RunState.REVIEWING.value
        assert RunState.PR_OPENED in VALID_TRANSITIONS[RunState.REVIEWING]
