"""Tests for LogStore tool call JSONL logging.

Verifies append_tool_log and get_tool_log work correctly for the
filesystem-based tool call log (supplementary to DB events).
"""

import json
from pathlib import Path
from uuid import uuid4

import pytest

from foundry.storage.log_store import LogStore


@pytest.fixture
def log_store(tmp_path: Path) -> LogStore:
    """Create a LogStore backed by a temporary directory."""
    return LogStore(artifact_base=str(tmp_path / "artifacts"))


@pytest.fixture
def run_id():
    return uuid4()


# ---------------------------------------------------------------------------
# append_tool_log
# ---------------------------------------------------------------------------


class TestAppendToolLog:
    async def test_creates_jsonl_file(self, log_store: LogStore, run_id):
        """append_tool_log must create the tool_log.jsonl file."""
        await log_store.append_tool_log(
            run_id=run_id,
            tool_name="bash",
            input_summary="git status",
            output_summary="On branch main",
            duration_ms=150,
            model="claude-sonnet-4-6",
        )

        log_path = log_store._tool_log_path(run_id)
        assert log_path.exists()

    async def test_writes_valid_json_line(self, log_store: LogStore, run_id):
        """Each appended entry must be a valid JSON line."""
        await log_store.append_tool_log(
            run_id=run_id,
            tool_name="edit",
            input_summary="Replace function signature",
            output_summary="File updated successfully",
            duration_ms=50,
        )

        log_path = log_store._tool_log_path(run_id)
        lines = log_path.read_text().strip().split("\n")
        assert len(lines) == 1

        entry = json.loads(lines[0])
        assert entry["tool_name"] == "edit"
        assert entry["input_summary"] == "Replace function signature"
        assert entry["output_summary"] == "File updated successfully"
        assert entry["duration_ms"] == 50
        assert entry["model"] is None
        assert "timestamp" in entry
        assert entry["run_id"] == str(run_id)

    async def test_appends_multiple_entries(self, log_store: LogStore, run_id):
        """Multiple calls must append to the same file."""
        for i in range(5):
            await log_store.append_tool_log(
                run_id=run_id,
                tool_name=f"tool_{i}",
                input_summary=f"input_{i}",
                output_summary=f"output_{i}",
                duration_ms=i * 100,
            )

        log_path = log_store._tool_log_path(run_id)
        lines = log_path.read_text().strip().split("\n")
        assert len(lines) == 5

        for i, line in enumerate(lines):
            entry = json.loads(line)
            assert entry["tool_name"] == f"tool_{i}"
            assert entry["duration_ms"] == i * 100

    async def test_truncates_long_input_summary(self, log_store: LogStore, run_id):
        """Input summary must be truncated to 2000 chars."""
        long_input = "x" * 5000
        await log_store.append_tool_log(
            run_id=run_id,
            tool_name="read",
            input_summary=long_input,
            output_summary="ok",
            duration_ms=10,
        )

        entries = await log_store.get_tool_log(run_id)
        assert len(entries[0]["input_summary"]) == 2000

    async def test_truncates_long_output_summary(self, log_store: LogStore, run_id):
        """Output summary must be truncated to 2000 chars."""
        long_output = "y" * 5000
        await log_store.append_tool_log(
            run_id=run_id,
            tool_name="bash",
            input_summary="ls",
            output_summary=long_output,
            duration_ms=10,
        )

        entries = await log_store.get_tool_log(run_id)
        assert len(entries[0]["output_summary"]) == 2000

    async def test_includes_model_when_provided(self, log_store: LogStore, run_id):
        """Model field must be set when provided."""
        await log_store.append_tool_log(
            run_id=run_id,
            tool_name="bash",
            input_summary="make build",
            output_summary="BUILD OK",
            duration_ms=5000,
            model="claude-opus-4-6",
        )

        entries = await log_store.get_tool_log(run_id)
        assert entries[0]["model"] == "claude-opus-4-6"

    async def test_creates_parent_directories(self, log_store: LogStore, run_id):
        """Parent directories must be created automatically."""
        # Verify the path doesn't exist yet
        log_path = log_store._tool_log_path(run_id)
        assert not log_path.parent.exists()

        await log_store.append_tool_log(
            run_id=run_id,
            tool_name="write",
            input_summary="Create new file",
            output_summary="File created",
            duration_ms=20,
        )

        assert log_path.exists()

    async def test_separate_logs_per_run(self, log_store: LogStore):
        """Different run IDs must have separate log files."""
        run_a = uuid4()
        run_b = uuid4()

        await log_store.append_tool_log(
            run_id=run_a,
            tool_name="tool_a",
            input_summary="a",
            output_summary="a",
            duration_ms=10,
        )
        await log_store.append_tool_log(
            run_id=run_b,
            tool_name="tool_b",
            input_summary="b",
            output_summary="b",
            duration_ms=20,
        )

        entries_a = await log_store.get_tool_log(run_a)
        entries_b = await log_store.get_tool_log(run_b)

        assert len(entries_a) == 1
        assert len(entries_b) == 1
        assert entries_a[0]["tool_name"] == "tool_a"
        assert entries_b[0]["tool_name"] == "tool_b"


# ---------------------------------------------------------------------------
# get_tool_log
# ---------------------------------------------------------------------------


class TestGetToolLog:
    async def test_returns_empty_list_for_nonexistent_run(self, log_store: LogStore):
        """get_tool_log must return [] for a run with no log file."""
        entries = await log_store.get_tool_log(uuid4())
        assert entries == []

    async def test_returns_all_entries_in_order(self, log_store: LogStore, run_id):
        """Entries must be returned in chronological (append) order."""
        tools = ["read", "edit", "bash", "write"]
        for tool in tools:
            await log_store.append_tool_log(
                run_id=run_id,
                tool_name=tool,
                input_summary=f"do {tool}",
                output_summary="ok",
                duration_ms=100,
            )

        entries = await log_store.get_tool_log(run_id)
        assert len(entries) == 4
        assert [e["tool_name"] for e in entries] == tools

    async def test_skips_empty_lines(self, log_store: LogStore, run_id):
        """Empty lines in the JSONL file must be skipped."""
        await log_store.append_tool_log(
            run_id=run_id,
            tool_name="bash",
            input_summary="cmd",
            output_summary="ok",
            duration_ms=10,
        )

        # Manually append an empty line
        log_path = log_store._tool_log_path(run_id)
        with open(log_path, "a") as f:
            f.write("\n\n")

        await log_store.append_tool_log(
            run_id=run_id,
            tool_name="edit",
            input_summary="cmd2",
            output_summary="ok2",
            duration_ms=20,
        )

        entries = await log_store.get_tool_log(run_id)
        assert len(entries) == 2

    async def test_skips_malformed_lines(self, log_store: LogStore, run_id):
        """Malformed JSON lines must be skipped without raising."""
        await log_store.append_tool_log(
            run_id=run_id,
            tool_name="bash",
            input_summary="cmd",
            output_summary="ok",
            duration_ms=10,
        )

        # Inject a malformed line
        log_path = log_store._tool_log_path(run_id)
        with open(log_path, "a") as f:
            f.write("this is not json\n")

        await log_store.append_tool_log(
            run_id=run_id,
            tool_name="edit",
            input_summary="cmd2",
            output_summary="ok2",
            duration_ms=20,
        )

        entries = await log_store.get_tool_log(run_id)
        assert len(entries) == 2
        assert entries[0]["tool_name"] == "bash"
        assert entries[1]["tool_name"] == "edit"

    async def test_entries_have_all_required_fields(self, log_store: LogStore, run_id):
        """Every entry must contain all ToolLogEntry fields."""
        await log_store.append_tool_log(
            run_id=run_id,
            tool_name="read",
            input_summary="/path/to/file",
            output_summary="file contents here",
            duration_ms=25,
            model="claude-haiku-4-5",
        )

        entries = await log_store.get_tool_log(run_id)
        entry = entries[0]

        required_fields = [
            "timestamp", "run_id", "tool_name",
            "input_summary", "output_summary",
            "duration_ms", "model",
        ]
        for field in required_fields:
            assert field in entry, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# tool_log_path
# ---------------------------------------------------------------------------


class TestToolLogPath:
    def test_path_includes_run_id(self, log_store: LogStore, run_id):
        """Tool log path must include the run ID."""
        path = log_store._tool_log_path(run_id)
        assert str(run_id) in str(path)

    def test_path_ends_with_jsonl(self, log_store: LogStore, run_id):
        """Tool log path must end with tool_log.jsonl."""
        path = log_store._tool_log_path(run_id)
        assert path.name == "tool_log.jsonl"

    def test_path_under_artifact_base(self, log_store: LogStore, run_id):
        """Tool log path must be under the artifact base directory."""
        path = log_store._tool_log_path(run_id)
        assert str(log_store.artifact_base) in str(path)
