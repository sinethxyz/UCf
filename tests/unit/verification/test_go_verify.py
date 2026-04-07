"""Tests for GoVerifier — mocks asyncio.create_subprocess_exec to avoid real Go toolchain."""

from unittest.mock import AsyncMock, patch

import pytest

from foundry.verification.go_verify import GoVerifier, StepResult, VerificationResult


def _make_proc(returncode: int = 0, stdout: bytes = b"", stderr: bytes = b"") -> AsyncMock:
    """Create a mock process with the given returncode, stdout, and stderr."""
    proc = AsyncMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    return proc


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_verify_all_pass():
    """When all three checks succeed, result.passed is True."""
    procs = [
        _make_proc(0, b"build ok"),
        _make_proc(0, b"vet ok"),
        _make_proc(0, b"test ok"),
    ]

    verifier = GoVerifier()
    with patch("foundry.verification.go_verify.asyncio") as mock_asyncio:
        mock_asyncio.create_subprocess_exec = AsyncMock(side_effect=procs)
        mock_asyncio.subprocess = __import__("asyncio").subprocess

        result = await verifier.verify("/fake/worktree")

    assert isinstance(result, VerificationResult)
    assert result.passed is True
    assert result.check_type == "go"
    assert "go_build" in result.output
    assert "go_vet" in result.output
    assert "go_test" in result.output
    assert result.duration_ms >= 0


async def test_verify_captures_stdout_and_stderr():
    """Output includes both stdout and stderr from each step."""
    procs = [
        _make_proc(0, b"compiled fine", b"warning: unused import"),
        _make_proc(0, b"vet clean"),
        _make_proc(0, b"PASS", b"ok  ./..."),
    ]

    verifier = GoVerifier()
    with patch("foundry.verification.go_verify.asyncio") as mock_asyncio:
        mock_asyncio.create_subprocess_exec = AsyncMock(side_effect=procs)
        mock_asyncio.subprocess = __import__("asyncio").subprocess

        result = await verifier.verify("/fake/worktree")

    assert result.passed is True
    assert "compiled fine" in result.output
    assert "unused import" in result.output
    assert "PASS" in result.output


# ---------------------------------------------------------------------------
# Failure: stop on first failure
# ---------------------------------------------------------------------------


async def test_verify_build_fails_stops_early():
    """When go build fails, vet and test are not run."""
    build_proc = _make_proc(1, b"", b"build error: missing package")

    verifier = GoVerifier()
    with patch("foundry.verification.go_verify.asyncio") as mock_asyncio:
        mock_asyncio.create_subprocess_exec = AsyncMock(return_value=build_proc)
        mock_asyncio.subprocess = __import__("asyncio").subprocess

        result = await verifier.verify("/fake/worktree")

    assert result.passed is False
    assert "build error" in result.output
    # Only called once (build), not three times
    assert mock_asyncio.create_subprocess_exec.call_count == 1


async def test_verify_vet_fails_stops_before_test():
    """When go vet fails, go test is not run."""
    procs = [
        _make_proc(0, b"build ok"),
        _make_proc(1, b"", b"vet error: unreachable code"),
    ]

    verifier = GoVerifier()
    with patch("foundry.verification.go_verify.asyncio") as mock_asyncio:
        mock_asyncio.create_subprocess_exec = AsyncMock(side_effect=procs)
        mock_asyncio.subprocess = __import__("asyncio").subprocess

        result = await verifier.verify("/fake/worktree")

    assert result.passed is False
    assert "go_build" in result.output
    assert "vet error" in result.output
    assert "go_test" not in result.output
    assert mock_asyncio.create_subprocess_exec.call_count == 2


async def test_verify_test_fails():
    """When go test fails, result is failed with test output included."""
    procs = [
        _make_proc(0, b"build ok"),
        _make_proc(0, b"vet ok"),
        _make_proc(1, b"--- FAIL: TestSomething", b"FAIL ./..."),
    ]

    verifier = GoVerifier()
    with patch("foundry.verification.go_verify.asyncio") as mock_asyncio:
        mock_asyncio.create_subprocess_exec = AsyncMock(side_effect=procs)
        mock_asyncio.subprocess = __import__("asyncio").subprocess

        result = await verifier.verify("/fake/worktree")

    assert result.passed is False
    assert "FAIL: TestSomething" in result.output
    assert mock_asyncio.create_subprocess_exec.call_count == 3


# ---------------------------------------------------------------------------
# Custom packages
# ---------------------------------------------------------------------------


async def test_verify_custom_packages():
    """When packages are specified, they are passed to each command."""
    procs = [
        _make_proc(0, b"ok"),
        _make_proc(0, b"ok"),
        _make_proc(0, b"ok"),
    ]

    verifier = GoVerifier()
    with patch("foundry.verification.go_verify.asyncio") as mock_asyncio:
        mock_asyncio.create_subprocess_exec = AsyncMock(side_effect=procs)
        mock_asyncio.subprocess = __import__("asyncio").subprocess

        result = await verifier.verify("/fake/worktree", packages=["./cmd/...", "./pkg/..."])

    assert result.passed is True

    # Check that the custom packages were passed through
    calls = mock_asyncio.create_subprocess_exec.call_args_list
    for call in calls:
        args = call[0]  # positional args
        assert "./cmd/..." in args
        assert "./pkg/..." in args


async def test_verify_default_packages():
    """Default package target is ./..."""
    procs = [
        _make_proc(0, b"ok"),
        _make_proc(0, b"ok"),
        _make_proc(0, b"ok"),
    ]

    verifier = GoVerifier()
    with patch("foundry.verification.go_verify.asyncio") as mock_asyncio:
        mock_asyncio.create_subprocess_exec = AsyncMock(side_effect=procs)
        mock_asyncio.subprocess = __import__("asyncio").subprocess

        await verifier.verify("/fake/worktree")

    calls = mock_asyncio.create_subprocess_exec.call_args_list
    for call in calls:
        args = call[0]
        assert "./..." in args


# ---------------------------------------------------------------------------
# Working directory
# ---------------------------------------------------------------------------


async def test_verify_uses_worktree_as_cwd():
    """Each subprocess should run in the worktree directory."""
    procs = [
        _make_proc(0, b"ok"),
        _make_proc(0, b"ok"),
        _make_proc(0, b"ok"),
    ]

    verifier = GoVerifier()
    with patch("foundry.verification.go_verify.asyncio") as mock_asyncio:
        mock_asyncio.create_subprocess_exec = AsyncMock(side_effect=procs)
        mock_asyncio.subprocess = __import__("asyncio").subprocess

        await verifier.verify("/my/worktree/path")

    calls = mock_asyncio.create_subprocess_exec.call_args_list
    for call in calls:
        assert call[1]["cwd"] == "/my/worktree/path"


# ---------------------------------------------------------------------------
# Duration tracking
# ---------------------------------------------------------------------------


async def test_verify_duration_is_positive():
    """Total duration_ms should be non-negative."""
    procs = [
        _make_proc(0, b"ok"),
        _make_proc(0, b"ok"),
        _make_proc(0, b"ok"),
    ]

    verifier = GoVerifier()
    with patch("foundry.verification.go_verify.asyncio") as mock_asyncio:
        mock_asyncio.create_subprocess_exec = AsyncMock(side_effect=procs)
        mock_asyncio.subprocess = __import__("asyncio").subprocess

        result = await verifier.verify("/fake/worktree")

    assert result.duration_ms >= 0


async def test_verify_failure_duration_is_positive():
    """Even on failure, duration should be tracked."""
    build_proc = _make_proc(1, b"", b"error")

    verifier = GoVerifier()
    with patch("foundry.verification.go_verify.asyncio") as mock_asyncio:
        mock_asyncio.create_subprocess_exec = AsyncMock(return_value=build_proc)
        mock_asyncio.subprocess = __import__("asyncio").subprocess

        result = await verifier.verify("/fake/worktree")

    assert result.passed is False
    assert result.duration_ms >= 0


# ---------------------------------------------------------------------------
# Output format
# ---------------------------------------------------------------------------


async def test_verify_output_contains_step_headers():
    """Output should contain === step_name (Nms) === headers for each completed step."""
    procs = [
        _make_proc(0, b"build output"),
        _make_proc(0, b"vet output"),
        _make_proc(1, b"test output", b"FAIL"),
    ]

    verifier = GoVerifier()
    with patch("foundry.verification.go_verify.asyncio") as mock_asyncio:
        mock_asyncio.create_subprocess_exec = AsyncMock(side_effect=procs)
        mock_asyncio.subprocess = __import__("asyncio").subprocess

        result = await verifier.verify("/fake/worktree")

    assert "=== go_build" in result.output
    assert "=== go_vet" in result.output
    assert "=== go_test" in result.output


# ---------------------------------------------------------------------------
# Per-step details
# ---------------------------------------------------------------------------


async def test_verify_all_pass_details():
    """On success, details contains three StepResult objects all with passed=True."""
    procs = [
        _make_proc(0, b"build ok"),
        _make_proc(0, b"vet ok"),
        _make_proc(0, b"PASS"),
    ]

    verifier = GoVerifier()
    with patch("foundry.verification.go_verify.asyncio") as mock_asyncio:
        mock_asyncio.create_subprocess_exec = AsyncMock(side_effect=procs)
        mock_asyncio.subprocess = __import__("asyncio").subprocess

        result = await verifier.verify("/fake/worktree")

    assert len(result.details) == 3
    assert all(isinstance(d, StepResult) for d in result.details)
    assert [d.step_name for d in result.details] == ["go_build", "go_vet", "go_test"]
    assert all(d.passed for d in result.details)
    assert all(d.duration_ms >= 0 for d in result.details)


async def test_verify_build_fail_details():
    """When build fails, details has one entry with passed=False."""
    build_proc = _make_proc(1, b"", b"compile error")

    verifier = GoVerifier()
    with patch("foundry.verification.go_verify.asyncio") as mock_asyncio:
        mock_asyncio.create_subprocess_exec = AsyncMock(return_value=build_proc)
        mock_asyncio.subprocess = __import__("asyncio").subprocess

        result = await verifier.verify("/fake/worktree")

    assert len(result.details) == 1
    assert result.details[0].step_name == "go_build"
    assert result.details[0].passed is False
    assert "compile error" in result.details[0].output


async def test_verify_vet_fail_details():
    """When vet fails, details has build (passed) + vet (failed)."""
    procs = [
        _make_proc(0, b"build ok"),
        _make_proc(1, b"", b"unreachable code"),
    ]

    verifier = GoVerifier()
    with patch("foundry.verification.go_verify.asyncio") as mock_asyncio:
        mock_asyncio.create_subprocess_exec = AsyncMock(side_effect=procs)
        mock_asyncio.subprocess = __import__("asyncio").subprocess

        result = await verifier.verify("/fake/worktree")

    assert len(result.details) == 2
    assert result.details[0].step_name == "go_build"
    assert result.details[0].passed is True
    assert result.details[1].step_name == "go_vet"
    assert result.details[1].passed is False
    assert "unreachable code" in result.details[1].output


async def test_verify_test_fail_details():
    """When test fails, details has build + vet (passed) + test (failed)."""
    procs = [
        _make_proc(0, b"build ok"),
        _make_proc(0, b"vet ok"),
        _make_proc(1, b"--- FAIL: TestFoo", b"FAIL"),
    ]

    verifier = GoVerifier()
    with patch("foundry.verification.go_verify.asyncio") as mock_asyncio:
        mock_asyncio.create_subprocess_exec = AsyncMock(side_effect=procs)
        mock_asyncio.subprocess = __import__("asyncio").subprocess

        result = await verifier.verify("/fake/worktree")

    assert len(result.details) == 3
    assert result.details[0].passed is True
    assert result.details[1].passed is True
    assert result.details[2].step_name == "go_test"
    assert result.details[2].passed is False
    assert "FAIL: TestFoo" in result.details[2].output


async def test_verify_step_output_includes_stderr():
    """Each StepResult.output includes both stdout and stderr."""
    procs = [
        _make_proc(0, b"stdout part", b"stderr part"),
        _make_proc(0, b"ok"),
        _make_proc(0, b"ok"),
    ]

    verifier = GoVerifier()
    with patch("foundry.verification.go_verify.asyncio") as mock_asyncio:
        mock_asyncio.create_subprocess_exec = AsyncMock(side_effect=procs)
        mock_asyncio.subprocess = __import__("asyncio").subprocess

        result = await verifier.verify("/fake/worktree")

    assert "stdout part" in result.details[0].output
    assert "stderr part" in result.details[0].output


async def test_verify_step_duration_tracked():
    """Each StepResult has a non-negative duration_ms."""
    procs = [
        _make_proc(0, b"ok"),
        _make_proc(0, b"ok"),
        _make_proc(0, b"ok"),
    ]

    verifier = GoVerifier()
    with patch("foundry.verification.go_verify.asyncio") as mock_asyncio:
        mock_asyncio.create_subprocess_exec = AsyncMock(side_effect=procs)
        mock_asyncio.subprocess = __import__("asyncio").subprocess

        result = await verifier.verify("/fake/worktree")

    for step in result.details:
        assert step.duration_ms >= 0
