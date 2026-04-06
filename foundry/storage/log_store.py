"""Structured run event logging.

All run state transitions and tool calls are logged as structured events.
"""

from uuid import UUID


class LogStore:
    """Manages structured event logging for runs."""

    async def log_event(self, run_id: UUID, event_type: str, data: dict) -> None:
        """Log a structured event for a run.

        Args:
            run_id: The run this event belongs to.
            event_type: Type of event (state_transition, tool_call, etc.).
            data: Event payload.
        """
        raise NotImplementedError

    async def get_events(self, run_id: UUID) -> list[dict]:
        """Retrieve all events for a run.

        Args:
            run_id: The run to get events for.

        Returns:
            List of event dicts ordered by timestamp.
        """
        raise NotImplementedError
