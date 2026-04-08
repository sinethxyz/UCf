"""Structured run event and tool call logging.

All run state transitions, tool calls, and model invocations are
logged as structured RunEvent records (DB) and tool call JSONL files (filesystem).

DB events: lifecycle milestones stored via run_queries.add_run_event().
JSONL tool logs: individual agent tool calls appended to
    {artifact_base}/runs/{run_id}/tool_log.jsonl
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict
from uuid import UUID

from foundry.contracts.run_models import RunEvent

logger = logging.getLogger(__name__)


class ToolLogEntry(TypedDict):
    """A single tool call log entry."""

    timestamp: str
    run_id: str
    tool_name: str
    input_summary: str
    output_summary: str
    duration_ms: int
    model: str | None


class LogStore:
    """Structured event and tool-call logging for runs.

    Provides two layers of logging:
    1. DB events via append_event / get_events / get_latest_event
       (delegates to run_queries for persistence in the run_events table).
    2. JSONL tool logs via append_tool_log / get_tool_log
       (filesystem-based, one file per run for high-frequency tool call capture).
    """

    def __init__(self, artifact_base: str = "artifacts") -> None:
        """Initialize the LogStore.

        Args:
            artifact_base: Root directory for artifact storage.
                Tool logs are written under {artifact_base}/runs/{run_id}/tool_log.jsonl.
        """
        self.artifact_base = Path(artifact_base)

    def _tool_log_path(self, run_id: UUID) -> Path:
        """Return the filesystem path for a run's tool log."""
        return self.artifact_base / "runs" / str(run_id) / "tool_log.jsonl"

    async def append_event(self, run_id: UUID, event: RunEvent) -> None:
        """Append a structured event to a run's event log.

        Delegates to the database via run_queries. This method exists
        for interface compatibility; callers that already have a DB session
        should use run_queries.add_run_event() directly.

        Args:
            run_id: The run this event belongs to.
            event: The RunEvent to persist.
        """
        from foundry.db.models import RunEvent as RunEventORM

        orm_event = RunEventORM(
            run_id=run_id,
            state=event.state.value if hasattr(event.state, "value") else event.state,
            message=event.message,
            metadata_=event.metadata or {},
            model_used=event.model_used,
            tokens_in=event.tokens_in,
            tokens_out=event.tokens_out,
            duration_ms=event.duration_ms,
        )
        # This requires a session — callers should use the DB layer directly.
        # Keeping this for interface compliance; raise if no session context.
        raise NotImplementedError(
            "Use run_queries.add_run_event() with a DB session for event persistence. "
            "LogStore.append_event exists for interface compliance only."
        )

    async def get_events(self, run_id: UUID) -> list[RunEvent]:
        """Retrieve all events for a run in chronological order.

        Delegates to the database via run_queries.

        Args:
            run_id: The run to get events for.

        Returns:
            List of RunEvent objects ordered by timestamp.
        """
        raise NotImplementedError(
            "Use run_queries.get_run_events() with a DB session for event retrieval. "
            "LogStore.get_events exists for interface compliance only."
        )

    async def get_latest_event(self, run_id: UUID) -> RunEvent | None:
        """Retrieve the most recent event for a run.

        Args:
            run_id: The run to get the latest event for.

        Returns:
            The most recent RunEvent, or None if no events exist.
        """
        raise NotImplementedError(
            "Use run_queries.get_run_events() with a DB session for event retrieval. "
            "LogStore.get_latest_event exists for interface compliance only."
        )

    async def append_tool_log(
        self,
        run_id: UUID,
        tool_name: str,
        input_summary: str,
        output_summary: str,
        duration_ms: int,
        model: str | None = None,
    ) -> None:
        """Append a tool call record to a run's JSONL tool log.

        Each call is written as a single JSON line to
        {artifact_base}/runs/{run_id}/tool_log.jsonl. This supplements
        the DB-level run events with fine-grained agent tool call data.

        Args:
            run_id: The run this tool call belongs to.
            tool_name: Name of the tool invoked (e.g. "bash", "edit", "read").
            input_summary: Abbreviated description of the tool input.
            output_summary: Abbreviated description of the tool output.
            duration_ms: Wall-clock time of the tool call in milliseconds.
            model: Model that triggered this tool call, if applicable.
        """
        log_path = self._tool_log_path(run_id)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        entry: ToolLogEntry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": str(run_id),
            "tool_name": tool_name,
            "input_summary": input_summary[:2000],
            "output_summary": output_summary[:2000],
            "duration_ms": duration_ms,
            "model": model,
        }

        line = json.dumps(entry, separators=(",", ":")) + "\n"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line)

        logger.debug(
            "Tool log: run=%s tool=%s duration=%dms",
            run_id, tool_name, duration_ms,
        )

    async def get_tool_log(self, run_id: UUID) -> list[ToolLogEntry]:
        """Read and parse a run's tool call log.

        Reads the JSONL file at {artifact_base}/runs/{run_id}/tool_log.jsonl
        and returns all entries as a list of dicts.

        Args:
            run_id: The run whose tool log to read.

        Returns:
            List of ToolLogEntry dicts in chronological order.
            Returns an empty list if no tool log exists.
        """
        log_path = self._tool_log_path(run_id)
        if not log_path.exists():
            return []

        entries: list[ToolLogEntry] = []
        with open(log_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    entries.append(entry)
                except json.JSONDecodeError:
                    logger.warning(
                        "Malformed JSONL at line %d in tool log for run %s",
                        line_num, run_id,
                    )
        return entries
