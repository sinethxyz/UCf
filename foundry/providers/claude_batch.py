"""Claude Message Batches API integration.

Used for bulk extraction and eval runs. Supports prompt caching
for system prompts shared across batch items.
"""

from typing import Any


class ClaudeBatchProvider:
    """Provider for Claude Message Batches API.

    Used for high-volume, cost-efficient batch processing of
    extraction and evaluation tasks.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key

    async def create_batch(
        self,
        system_prompt: str,
        items: list[dict],
        model: str = "claude-haiku-4-5-20251001",
        output_schema: dict[str, Any] | None = None,
    ) -> str:
        """Submit a batch of messages for processing.

        Args:
            system_prompt: Shared system prompt (cached across items).
            items: List of message dicts, one per batch item.
            model: Model identifier (default: claude-haiku-4-5-20251001).
            output_schema: Optional JSON Schema for structured output.

        Returns:
            Anthropic batch ID for polling.
        """
        raise NotImplementedError("Phase 1")

    async def poll_batch(self, batch_id: str) -> dict:
        """Poll a batch job for completion status.

        Args:
            batch_id: The Anthropic batch ID.

        Returns:
            Dict with 'state', 'completed' count, and 'failed' count.
        """
        raise NotImplementedError("Phase 1")

    async def get_results(self, batch_id: str) -> list[dict]:
        """Retrieve results for a completed batch.

        Args:
            batch_id: The Anthropic batch ID.

        Returns:
            List of result dicts, one per batch item.
        """
        raise NotImplementedError("Phase 1")

    async def cancel_batch(self, batch_id: str) -> None:
        """Cancel a running batch job.

        Args:
            batch_id: The Anthropic batch ID to cancel.
        """
        raise NotImplementedError("Phase 1")
