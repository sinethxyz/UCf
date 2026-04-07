"""Structured run event logging.

All run state transitions, tool calls, and model invocations are
logged as structured RunEvent records.
"""

from uuid import UUID

from foundry.contracts.run_models import RunEvent


class LogStore:
    """Structured event logging for runs.

    Persists RunEvent objects for full run traceability and replay.
    """

    async def append_event(self, run_id: UUID, event: RunEvent) -> None:
        """Append a structured event to a run's event log.

        Args:
            run_id: The run this event belongs to.
            event: The RunEvent to persist.
        """
        raise NotImplementedError("Phase 1")

    async def get_events(self, run_id: UUID) -> list[RunEvent]:
        """Retrieve all events for a run in chronological order.

        Args:
            run_id: The run to get events for.

        Returns:
            List of RunEvent objects ordered by timestamp.
        """
        raise NotImplementedError("Phase 1")

    async def get_latest_event(self, run_id: UUID) -> RunEvent | None:
        """Retrieve the most recent event for a run.

        Args:
            run_id: The run to get the latest event for.

        Returns:
            The most recent RunEvent, or None if no events exist.
        """
        raise NotImplementedError("Phase 1")
