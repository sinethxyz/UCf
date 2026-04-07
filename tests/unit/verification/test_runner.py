"""Tests for VerificationRunner — dispatches to the right verifier based on changed files."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from foundry.verification.go_verify import VerificationResult
from foundry.verification.runner import VerificationRunner


def _go_result(passed: bool = True) -> VerificationResult:
    return VerificationResult(check_type="go", passed=passed, output="go output", duration_ms=100)


# ---------------------------------------------------------------------------
# Go file detection
# ---------------------------------------------------------------------------


async def test_run_all_with_go_files():
    """When .go files are present, GoVerifier is called."""
    runner = VerificationRunner()
    runner.go_verifier.verify = AsyncMock(return_value=_go_result(True))

    results, passed = await runner.run_all("/fake/worktree", ["handler.go", "handler_test.go"])

    assert len(results) == 1
    assert results[0].check_type == "go"
    assert results[0].passed is True
    assert passed is True
    runner.go_verifier.verify.assert_awaited_once_with("/fake/worktree")


async def test_run_all_go_files_in_subdirs():
    """Go files in subdirectories should still trigger the verifier."""
    runner = VerificationRunner()
    runner.go_verifier.verify = AsyncMock(return_value=_go_result(True))

    results, passed = await runner.run_all("/fake/worktree", ["services/api/handler.go"])

    assert len(results) == 1
    assert results[0].check_type == "go"
    assert passed is True
    runner.go_verifier.verify.assert_awaited_once()


async def test_run_all_go_failure_propagates():
    """A failed Go verification should propagate passed=False."""
    runner = VerificationRunner()
    runner.go_verifier.verify = AsyncMock(return_value=_go_result(False))

    results, passed = await runner.run_all("/fake/worktree", ["main.go"])

    assert len(results) == 1
    assert results[0].passed is False
    assert passed is False


# ---------------------------------------------------------------------------
# No applicable verifiers
# ---------------------------------------------------------------------------


async def test_run_all_no_matching_files():
    """When no known file types are present, a 'none' result is returned."""
    runner = VerificationRunner()
    runner.go_verifier.verify = AsyncMock()

    results, passed = await runner.run_all("/fake/worktree", ["README.md", "docs/guide.txt"])

    assert len(results) == 1
    assert results[0].check_type == "none"
    assert results[0].passed is True
    assert results[0].duration_ms == 0
    assert passed is True
    runner.go_verifier.verify.assert_not_awaited()


async def test_run_all_empty_changed_files():
    """Empty changed_files list should return 'none' result."""
    runner = VerificationRunner()
    runner.go_verifier.verify = AsyncMock()

    results, passed = await runner.run_all("/fake/worktree", [])

    assert len(results) == 1
    assert results[0].check_type == "none"
    assert results[0].passed is True
    assert passed is True
    runner.go_verifier.verify.assert_not_awaited()


# ---------------------------------------------------------------------------
# Mixed file types
# ---------------------------------------------------------------------------


async def test_run_all_mixed_go_and_non_go():
    """When both .go and non-.go files are present, only Go verifier runs."""
    runner = VerificationRunner()
    runner.go_verifier.verify = AsyncMock(return_value=_go_result(True))

    results, passed = await runner.run_all(
        "/fake/worktree",
        ["handler.go", "README.md", "config.yaml"],
    )

    assert len(results) == 1
    assert results[0].check_type == "go"
    assert passed is True
    runner.go_verifier.verify.assert_awaited_once()


async def test_run_all_ts_files_deferred():
    """.ts files don't trigger any verifier — dispatch hook only."""
    runner = VerificationRunner()
    runner.go_verifier.verify = AsyncMock()

    results, passed = await runner.run_all("/fake/worktree", ["component.ts", "page.tsx"])

    # TS verifier is deferred, so we get the 'none' fallback
    assert len(results) == 1
    assert results[0].check_type == "none"
    assert passed is True
    runner.go_verifier.verify.assert_not_awaited()


async def test_run_all_schema_files_deferred():
    """.schema.json files don't trigger any verifier — dispatch hook only."""
    runner = VerificationRunner()
    runner.go_verifier.verify = AsyncMock()

    results, passed = await runner.run_all("/fake/worktree", ["event.schema.json"])

    assert len(results) == 1
    assert results[0].check_type == "none"
    assert passed is True
    runner.go_verifier.verify.assert_not_awaited()


async def test_run_all_mixed_go_and_ts():
    """When both .go and .ts files are present, only Go verifier runs (TS deferred)."""
    runner = VerificationRunner()
    runner.go_verifier.verify = AsyncMock(return_value=_go_result(True))

    results, passed = await runner.run_all(
        "/fake/worktree",
        ["handler.go", "page.tsx", "component.ts"],
    )

    assert len(results) == 1
    assert results[0].check_type == "go"
    assert passed is True
    runner.go_verifier.verify.assert_awaited_once()


# ---------------------------------------------------------------------------
# Worktree path passthrough
# ---------------------------------------------------------------------------


async def test_run_all_passes_worktree_path():
    """The worktree_path is forwarded to the Go verifier."""
    runner = VerificationRunner()
    runner.go_verifier.verify = AsyncMock(return_value=_go_result(True))

    await runner.run_all("/specific/worktree", ["main.go"])

    runner.go_verifier.verify.assert_awaited_once_with("/specific/worktree")


# ---------------------------------------------------------------------------
# Overall pass/fail aggregation
# ---------------------------------------------------------------------------


async def test_run_all_overall_passed_true():
    """overall_passed is True when all results pass."""
    runner = VerificationRunner()
    runner.go_verifier.verify = AsyncMock(return_value=_go_result(True))

    _, passed = await runner.run_all("/fake/worktree", ["main.go"])

    assert passed is True


async def test_run_all_overall_passed_false():
    """overall_passed is False when any result fails."""
    runner = VerificationRunner()
    runner.go_verifier.verify = AsyncMock(return_value=_go_result(False))

    _, passed = await runner.run_all("/fake/worktree", ["main.go"])

    assert passed is False


async def test_run_all_no_verifiers_overall_passed():
    """When no verifiers run, overall_passed is True (none result passes)."""
    runner = VerificationRunner()

    _, passed = await runner.run_all("/fake/worktree", ["README.md"])

    assert passed is True


# ---------------------------------------------------------------------------
# DB persistence
# ---------------------------------------------------------------------------


async def test_run_all_writes_to_db_when_session_provided():
    """When run_id and session are given, verification rows are persisted."""
    runner = VerificationRunner()
    runner.go_verifier.verify = AsyncMock(return_value=_go_result(True))

    mock_session = AsyncMock()
    run_id = uuid.uuid4()

    with patch("foundry.verification.runner.VRModel", create=True) as MockVRModel:
        # Patch the import inside run_all
        mock_vr_cls = MagicMock()
        with patch.dict(
            "sys.modules",
            {"foundry.db.models": MagicMock(VerificationResult=mock_vr_cls)},
        ):
            results, passed = await runner.run_all(
                "/fake/worktree",
                ["main.go"],
                run_id=run_id,
                session=mock_session,
            )

    assert passed is True
    assert mock_session.add.call_count == 1
    mock_session.flush.assert_awaited_once()


async def test_run_all_no_db_write_without_session():
    """When session is None, no DB writes happen."""
    runner = VerificationRunner()
    runner.go_verifier.verify = AsyncMock(return_value=_go_result(True))

    results, passed = await runner.run_all("/fake/worktree", ["main.go"])

    assert passed is True
    # No assertion on session — just verify no errors


async def test_run_all_no_db_write_without_run_id():
    """When run_id is None, no DB writes happen even with a session."""
    runner = VerificationRunner()
    runner.go_verifier.verify = AsyncMock(return_value=_go_result(True))

    mock_session = AsyncMock()

    results, passed = await runner.run_all(
        "/fake/worktree",
        ["main.go"],
        session=mock_session,
    )

    assert passed is True
    mock_session.add.assert_not_called()
    mock_session.flush.assert_not_awaited()


async def test_run_all_db_persists_multiple_results():
    """When multiple verifiers run, each result is persisted."""
    runner = VerificationRunner()
    go_result = _go_result(True)
    runner.go_verifier.verify = AsyncMock(return_value=go_result)

    mock_session = AsyncMock()
    run_id = uuid.uuid4()

    with patch.dict(
        "sys.modules",
        {"foundry.db.models": MagicMock(VerificationResult=MagicMock())},
    ):
        results, passed = await runner.run_all(
            "/fake/worktree",
            ["handler.go"],
            run_id=run_id,
            session=mock_session,
        )

    assert mock_session.add.call_count == len(results)
    mock_session.flush.assert_awaited_once()


async def test_run_all_db_truncates_output():
    """Output stored in DB is truncated to 10,000 characters."""
    long_output = "x" * 20_000
    big_result = VerificationResult(
        check_type="go", passed=True, output=long_output, duration_ms=50,
    )

    runner = VerificationRunner()
    runner.go_verifier.verify = AsyncMock(return_value=big_result)

    mock_session = AsyncMock()
    run_id = uuid.uuid4()

    mock_vr_cls = MagicMock()
    with patch.dict(
        "sys.modules",
        {"foundry.db.models": MagicMock(VerificationResult=mock_vr_cls)},
    ):
        await runner.run_all(
            "/fake/worktree",
            ["main.go"],
            run_id=run_id,
            session=mock_session,
        )

    # The VRModel was called with truncated output
    call_kwargs = mock_vr_cls.call_args[1]
    assert len(call_kwargs["output"]) == 10_000
