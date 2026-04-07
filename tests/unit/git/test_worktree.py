"""Tests for WorktreeManager: create, cleanup, and helpers."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from foundry.git.worktree import WorktreeManager, _slugify


# -- _slugify -----------------------------------------------------------------


class TestSlugify:
    def test_basic_text(self):
        assert _slugify("Fix pagination bug") == "fix-pagination-bug"

    def test_special_characters_replaced(self):
        assert _slugify("Add GET /v1/companies/{id}") == "add-get-v1-companies-id"

    def test_max_length_truncation(self):
        result = _slugify("a very long title that exceeds the limit", max_length=10)
        assert len(result) <= 10

    def test_trailing_hyphens_stripped_after_truncation(self):
        # "abcdefghij-" truncated at 11 then rstripped
        result = _slugify("abcdefghij klmnop", max_length=11)
        assert not result.endswith("-")

    def test_empty_string(self):
        assert _slugify("") == ""

    def test_already_slugified(self):
        assert _slugify("already-good") == "already-good"

    def test_leading_trailing_whitespace(self):
        assert _slugify("  hello world  ") == "hello-world"

    def test_consecutive_special_chars(self):
        assert _slugify("foo---bar___baz") == "foo-bar-baz"


# -- WorktreeManager.create ---------------------------------------------------


class TestWorktreeCreate:
    @pytest.fixture
    def manager(self, tmp_path: Path) -> WorktreeManager:
        return WorktreeManager(
            repo_path=str(tmp_path / "repo"),
            worktree_base=str(tmp_path / "worktrees"),
        )

    async def test_create_calls_git_worktree_add(self, manager: WorktreeManager):
        run_id = uuid4()
        branch = "foundry/bug-fix-pagination"

        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            result = await manager.create("unicorn-app", branch, run_id)

        # Verify git command
        mock_exec.assert_called_once()
        args = mock_exec.call_args
        cmd = args[0]
        assert cmd[0] == "git"
        assert cmd[1] == "worktree"
        assert cmd[2] == "add"
        assert cmd[3] == "-b"
        assert cmd[4] == branch
        assert str(run_id) in cmd[5]  # worktree path contains run_id
        assert cmd[6] == "HEAD"

    async def test_create_returns_worktree_path(self, manager: WorktreeManager):
        run_id = uuid4()

        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await manager.create("unicorn-app", "foundry/test", run_id)

        expected = str(Path(manager.worktree_base) / str(run_id))
        assert result == expected

    async def test_create_makes_parent_dirs(self, manager: WorktreeManager, tmp_path: Path):
        run_id = uuid4()

        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            await manager.create("unicorn-app", "foundry/test", run_id)

        # The parent directory (worktree_base) should have been created
        assert Path(manager.worktree_base).exists()

    async def test_create_raises_on_git_failure(self, manager: WorktreeManager):
        run_id = uuid4()

        mock_proc = AsyncMock()
        mock_proc.returncode = 128
        mock_proc.communicate = AsyncMock(
            return_value=(b"", b"fatal: branch already exists")
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with pytest.raises(RuntimeError, match="Failed to create worktree"):
                await manager.create("unicorn-app", "foundry/test", run_id)

    async def test_create_sets_cwd_to_repo_path(self, manager: WorktreeManager):
        run_id = uuid4()

        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            await manager.create("unicorn-app", "foundry/test", run_id)

        kwargs = mock_exec.call_args[1]
        assert kwargs["cwd"] == str(manager.repo_path)


# -- WorktreeManager.cleanup --------------------------------------------------


class TestWorktreeCleanup:
    @pytest.fixture
    def manager(self, tmp_path: Path) -> WorktreeManager:
        return WorktreeManager(
            repo_path=str(tmp_path / "repo"),
            worktree_base=str(tmp_path / "worktrees"),
        )

    async def test_cleanup_calls_git_worktree_remove(self, manager: WorktreeManager):
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            await manager.cleanup("/tmp/foundry-worktrees/some-run-id")

        args = mock_exec.call_args[0]
        assert args[0] == "git"
        assert args[1] == "worktree"
        assert args[2] == "remove"
        assert args[3] == "--force"
        assert args[4] == "/tmp/foundry-worktrees/some-run-id"

    async def test_cleanup_removes_remaining_directory(self, manager: WorktreeManager, tmp_path: Path):
        # Create a directory that simulates a leftover worktree
        leftover = tmp_path / "leftover-worktree"
        leftover.mkdir()
        (leftover / "somefile.txt").write_text("data")

        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            await manager.cleanup(str(leftover))

        assert not leftover.exists()

    async def test_cleanup_tolerates_missing_directory(self, manager: WorktreeManager):
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            # Should not raise even if path doesn't exist
            await manager.cleanup("/nonexistent/path")


# -- Deferred methods ---------------------------------------------------------


class TestDeferredMethods:
    @pytest.fixture
    def manager(self, tmp_path: Path) -> WorktreeManager:
        return WorktreeManager(
            repo_path=str(tmp_path / "repo"),
            worktree_base=str(tmp_path / "worktrees"),
        )

    async def test_cleanup_stale_raises_not_implemented(self, manager: WorktreeManager):
        with pytest.raises(NotImplementedError, match="Phase 1"):
            await manager.cleanup_stale()

    async def test_list_active_raises_not_implemented(self, manager: WorktreeManager):
        with pytest.raises(NotImplementedError, match="Phase 1"):
            await manager.list_active()
