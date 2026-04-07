"""Tests for VerificationRunner — dispatches to the right verifier based on changed files."""

from unittest.mock import AsyncMock, patch

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

    results = await runner.run_all("/fake/worktree", ["handler.go", "handler_test.go"])

    assert len(results) == 1
    assert results[0].check_type == "go"
    assert results[0].passed is True
    runner.go_verifier.verify.assert_awaited_once_with("/fake/worktree")


async def test_run_all_go_files_in_subdirs():
    """Go files in subdirectories should still trigger the verifier."""
    runner = VerificationRunner()
    runner.go_verifier.verify = AsyncMock(return_value=_go_result(True))

    results = await runner.run_all("/fake/worktree", ["services/api/handler.go"])

    assert len(results) == 1
    assert results[0].check_type == "go"
    runner.go_verifier.verify.assert_awaited_once()


async def test_run_all_go_failure_propagates():
    """A failed Go verification should propagate passed=False."""
    runner = VerificationRunner()
    runner.go_verifier.verify = AsyncMock(return_value=_go_result(False))

    results = await runner.run_all("/fake/worktree", ["main.go"])

    assert len(results) == 1
    assert results[0].passed is False


# ---------------------------------------------------------------------------
# No applicable verifiers
# ---------------------------------------------------------------------------


async def test_run_all_no_matching_files():
    """When no known file types are present, a 'none' result is returned."""
    runner = VerificationRunner()
    runner.go_verifier.verify = AsyncMock()

    results = await runner.run_all("/fake/worktree", ["README.md", "docs/guide.txt"])

    assert len(results) == 1
    assert results[0].check_type == "none"
    assert results[0].passed is True
    assert results[0].duration_ms == 0
    runner.go_verifier.verify.assert_not_awaited()


async def test_run_all_empty_changed_files():
    """Empty changed_files list should return 'none' result."""
    runner = VerificationRunner()
    runner.go_verifier.verify = AsyncMock()

    results = await runner.run_all("/fake/worktree", [])

    assert len(results) == 1
    assert results[0].check_type == "none"
    assert results[0].passed is True
    runner.go_verifier.verify.assert_not_awaited()


# ---------------------------------------------------------------------------
# Mixed file types
# ---------------------------------------------------------------------------


async def test_run_all_mixed_go_and_non_go():
    """When both .go and non-.go files are present, only Go verifier runs."""
    runner = VerificationRunner()
    runner.go_verifier.verify = AsyncMock(return_value=_go_result(True))

    results = await runner.run_all(
        "/fake/worktree",
        ["handler.go", "README.md", "config.yaml"],
    )

    assert len(results) == 1
    assert results[0].check_type == "go"
    runner.go_verifier.verify.assert_awaited_once()


async def test_run_all_ts_files_deferred():
    """.ts files don't trigger any verifier in Phase 1."""
    runner = VerificationRunner()
    runner.go_verifier.verify = AsyncMock()

    results = await runner.run_all("/fake/worktree", ["component.ts", "page.tsx"])

    # TS verifier is deferred, so we get the 'none' fallback
    assert len(results) == 1
    assert results[0].check_type == "none"
    runner.go_verifier.verify.assert_not_awaited()


async def test_run_all_schema_files_deferred():
    """.schema.json files don't trigger any verifier in Phase 1."""
    runner = VerificationRunner()
    runner.go_verifier.verify = AsyncMock()

    results = await runner.run_all("/fake/worktree", ["event.schema.json"])

    assert len(results) == 1
    assert results[0].check_type == "none"
    runner.go_verifier.verify.assert_not_awaited()


# ---------------------------------------------------------------------------
# Worktree path passthrough
# ---------------------------------------------------------------------------


async def test_run_all_passes_worktree_path():
    """The worktree_path is forwarded to the Go verifier."""
    runner = VerificationRunner()
    runner.go_verifier.verify = AsyncMock(return_value=_go_result(True))

    await runner.run_all("/specific/worktree", ["main.go"])

    runner.go_verifier.verify.assert_awaited_once_with("/specific/worktree")
