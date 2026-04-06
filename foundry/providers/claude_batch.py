"""Claude Message Batches API integration.

Used for bulk extraction and eval runs. Supports prompt caching
for system prompts shared across batch items.
"""


class ClaudeBatchProvider:
    """Provider for Claude Message Batches API."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key

    async def create_batch(
        self,
        model: str,
        system: str,
        items: list[dict],
    ) -> str:
        """Submit a batch of messages for processing.

        Args:
            model: Model identifier.
            system: Shared system prompt (cached across items).
            items: List of message dicts, one per batch item.

        Returns:
            Anthropic batch ID for polling.
        """
        raise NotImplementedError

    async def poll_batch(self, batch_id: str) -> dict:
        """Poll a batch job for completion status.

        Args:
            batch_id: The Anthropic batch ID.

        Returns:
            Batch status dict with state and results.
        """
        raise NotImplementedError
